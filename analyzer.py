import asyncio
import random
import re
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright
import gspread

# --- 설정 ---
SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ"

PRODUCTS = {
    "콘드1200": [
        "https://prod.danawa.com/info/?pcode=13412984", "https://prod.danawa.com/info/?pcode=13413059",
        "https://prod.danawa.com/info/?pcode=13413086", "https://prod.danawa.com/info/?pcode=13413254",
        "https://prod.danawa.com/info/?pcode=13678937", "https://prod.danawa.com/info/?pcode=13413314"
    ]
}

async def get_mall_set_price(page, url, idx_name):
    try:
        print(f"🔎 {idx_name} 분석 시작: {url}")
        await page.goto(url, wait_until="load", timeout=60000)
        await asyncio.sleep(6)
        
        # 오른쪽 '쇼핑몰별 최저가' 섹션이 로드될 때까지 스크롤
        await page.evaluate("window.scrollTo(0, 800)")
        await asyncio.sleep(2)

        # [핵심] 자바스크립트로 '유료배송'이면서 '지마켓/옥션'인 첫 번째 링크 찾기
        target_link = await page.evaluate("""
            () => {
                // 오른쪽 섹션 혹은 메인 리스트 영역 확보
                const container = document.querySelector('#productPriceComparison') || document;
                const rows = container.querySelectorAll('.diff_item, .prc_line');
                
                for (const row of rows) {
                    const text = row.innerText;
                    const mallName = row.querySelector('.mall_nm')?.innerText || "";
                    
                    // 조건: '무료배송'이 아니고 + ('배송비' 문구가 있거나 '유료'판단) + (지마켓/옥션 우선)
                    const isFree = text.includes('무료배송') || text.includes('무료');
                    const isTargetMall = mallName.includes('G마켓') || mallName.includes('옥션') || text.includes('G마켓') || text.includes('옥션');
                    
                    if (!isFree && isTargetMall) {
                        const aTag = row.querySelector('a.p_link, a.btn_buy, .prc_c a');
                        if (aTag && aTag.href) return aTag.href;
                    }
                }
                return null;
            }
        """)

        # 만약 위에서 못찾았다면 (지마켓/옥션이 유료배송 리스트에 없을 때) 차선책으로 1순위 유료배송 링크 시도
        if not target_link:
            target_link = await page.evaluate("""
                () => {
                    const container = document.querySelector('#productPriceComparison') || document;
                    const rows = container.querySelectorAll('.diff_item');
                    for (const row of rows) {
                        if (!row.innerText.includes('무료배송')) {
                            const aTag = row.querySelector('a.p_link, a.btn_buy');
                            if (aTag) return aTag.href;
                        }
                    }
                    return null;
                }
            """)

        if not target_link:
            print(f"   ❌ {idx_name}: 조건에 맞는 유료배송 링크를 찾지 못함")
            return "업체미발견", 0

        # 판매처 이동
        print(f"   🚀 판매처 이동...")
        await page.goto(target_link, wait_until="load", timeout=90000)
        await asyncio.sleep(10)

        # 지마켓/옥션 검색 리스트 대응 (한 번 더 클릭해서 상세페이지로)
        if "gmarket.co.kr/n/search" in page.url or "auction.co.kr" in page.url and "keyword=" in page.url:
            print("   🖱️ 지마켓/옥션 리스트 발견, 상세페이지 진입 시도...")
            try:
                # 리스트의 첫 번째 상품 클릭
                await page.click(".box__item-container a, .image__item, .item_title a", timeout=10000)
                await asyncio.sleep(8)
            except: pass

        final_url = page.url
        print(f"   🔗 최종 도착: {final_url[:60]}...")

        mall_name = "기타몰"
        set_price = 0

        # 가격 추출 (설정가/판매가)
        if "auction.co.kr" in final_url or "gmarket.co.kr" in final_url:
            mall_name = "옥션" if "auction" in final_url else "지마켓"
            # 지마켓 3단계 상세페이지의 가격 태그들
            for s in ["span.price_inner__price", "del.original-price", "#lblSellingPrice", "strong.price_real_value", ".price_real"]:
                el = await page.query_selector(s)
                if el:
                    txt = await el.inner_text()
                    num = re.sub(r'[^0-9]', '', txt)
                    if num and int(num) > 1000:
                        set_price = int(num)
                        print(f"   💰 가격 발견: {set_price}")
                        break
        
        return mall_name, set_price

    except Exception as e:
        print(f"   ⚠️ 에러 발생: {str(e)[:50]}")
        return "에러", 0

async def main():
    creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
    creds = json.loads(creds_raw)
    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_key(SH_ID)
    wks = sh.worksheet("정산가분석")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for prod_name, urls in PRODUCTS.items():
            print(f"\n--- {prod_name} 수집 시작 ---")
            for idx, url in enumerate(urls):
                mall, price = await get_mall_set_price(page, url, f"{idx+1}개입")
                if price > 0:
                    wks.append_row([datetime.now().strftime('%Y-%m-%d %H:%M:%S'), prod_name, f"{idx+1}개입", mall, price, int(price*0.85)])
                    print(f"   ✅ 성공: {price}원")
                else:
                    print(f"   ❌ 실패")
                await asyncio.sleep(random.randint(10, 15))
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
