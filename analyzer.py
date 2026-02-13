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
        # 다나와 접속
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        await page.evaluate("window.scrollTo(0, 1000)")

        # 1. 유료배송 지마켓/옥션/롯데온 링크 추출 (정밀도 강화)
        target_link = await page.evaluate("""
            () => {
                const container = document.querySelector('#productPriceComparison') || document;
                const rows = container.querySelectorAll('.diff_item, .prc_line');
                for (const row of rows) {
                    const text = row.innerText;
                    if (text.includes('무료배송')) continue;
                    
                    // 지마켓, 옥션, 롯데온 중 하나라도 걸리면 추출
                    if (text.includes('G마켓') || text.includes('옥션') || text.includes('롯데')) {
                        const a = row.querySelector('a.p_link, a.btn_buy');
                        if (a && a.href) return a.href;
                    }
                }
                return null;
            }
        """)

        if not target_link:
            print(f"   ❌ {idx_name}: 적절한 유료배송 링크 없음")
            return "업체미발견", 0

        # 2. 판매처 이동
        print(f"   🚀 판매처 이동...")
        await page.goto(target_link, wait_until="load", timeout=90000)
        await asyncio.sleep(8)

        # 3. [지마켓/옥션] 검색 결과 페이지라면 무조건 첫 상품 클릭
        if "search" in page.url or "Search" in page.url:
            print("   🖱️ 리스트 페이지 감지, 상품 클릭 시도...")
            # 지마켓/옥션 검색 결과의 다양한 상품 링크 선택자
            selectors = [".box__item-container a", ".image__item", ".item_title a", "#item_img_0", ".list_unit a"]
            for s in selectors:
                try:
                    target = await page.query_selector(s)
                    if target:
                        await target.click()
                        await asyncio.sleep(8)
                        break
                except: continue

        # 4. [롯데온] 보안 우회 및 로딩 대기
        if "lotteon.com" in page.url:
            print("   🛡️ 롯데온 감지, 데이터 로딩 대기...")
            await asyncio.sleep(5)
            await page.evaluate("window.scrollTo(0, 500)")

        final_url = page.url
        print(f"   🔗 최종 도착: {final_url[:60]}...")

        # 5. 가격 추출 (모든 수단 동원)
        set_price = 0
        mall_name = "지마켓" if "gmarket" in final_url else "옥션" if "auction" in final_url else "롯데온" if "lotteon" in final_url else "기타몰"

        # 시각적으로 보이는 가격 태그 모두 뒤지기
        price_selectors = [
            "span.price_inner__price", "del.original-price", "#lblSellingPrice", 
            ".price_real", ".price_main", "strong.price_real_value", ".num", ".price",
            "span[class*='price']", "strong[class*='price']"
        ]

        for s in price_selectors:
            try:
                elements = await page.query_selector_all(s)
                for el in elements:
                    txt = await el.inner_text()
                    num = int(re.sub(r'[^0-9]', '', txt))
                    if 10000 < num < 500000: # 너무 작거나 큰 가격 제외 (보통 영양제 세트가)
                        set_price = num
                        print(f"   💰 가격 발견 ({s}): {set_price}")
                        return mall_name, set_price
            except: continue

        return mall_name, 0

    except Exception as e:
        print(f"   ⚠️ 에러: {str(e)[:50]}")
        return "에러", 0

async def main():
    creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
    creds = json.loads(creds_raw)
    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_key(SH_ID)
    wks = sh.worksheet("정산가분석")

    async with async_playwright() as p:
        # 롯데온 등 보안이 까다로운 곳을 위해 스텔스 모드 환경 설정
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            locale="ko-KR"
        )
        page = await context.new_page()

        for prod_name, urls in PRODUCTS.items():
            print(f"\n--- {prod_name} 수집 시작 ---")
            for idx, url in enumerate(urls):
                mall, price = await get_mall_set_price(page, url, f"{idx+1}개입")
                if price > 0:
                    wks.append_row([datetime.now().strftime('%Y-%m-%d %H:%M:%S'), prod_name, f"{idx+1}개입", mall, price, int(price*0.85)])
                    print(f"   ✅ 수집 완료: {price}원")
                else:
                    print(f"   ❌ 가격 추출 실패")
                await asyncio.sleep(random.randint(12, 18))
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
