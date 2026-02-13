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
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # 1. 다나와 리스트 렌더링 대기
        await asyncio.sleep(5)
        await page.evaluate("window.scrollTo(0, 1000)")
        try:
            await page.wait_for_selector(".diff_item", timeout=15000)
            print("   ✅ 다나와 리스트 확인")
        except: pass

        # 2. 유료배송 1위 업체 링크 추출
        target_link = await page.evaluate("""
            () => {
                const items = document.querySelectorAll('.diff_item');
                for (const item of items) {
                    const text = item.innerText;
                    if (!text.includes('무료배송') && (text.includes('배송비') || text.includes('원'))) {
                        const aTag = item.querySelector('.prc_c a, .mall_nm a, .btn_buy a');
                        if (aTag && aTag.href) return aTag.href;
                    }
                }
                return null;
            }
        """)

        if not target_link:
            print(f"   ❌ {idx_name}: 다나와 링크 추출 실패")
            return "업체미발견", 0

        # 3. 쇼핑몰 이동 (1차 진입: 보통 검색 결과 페이지)
        print(f"   🚀 판매처 이동 시작...")
        await page.goto(target_link, wait_until="load", timeout=90000)
        await asyncio.sleep(8)
        
        # [지마켓 전용] 검색 결과 페이지라면 첫 번째 상품 클릭해서 상세페이지 진입
        if "gmarket.co.kr/n/search" in page.url:
            print("   🖱️ 지마켓 검색 리스트 발견, 상세페이지로 클릭 이동...")
            try:
                # 첫 번째 상품 이미지나 제목 클릭
                await page.click(".box__item-container a, .image__item", timeout=10000)
                await asyncio.sleep(8)
            except:
                print("   ⚠️ 클릭 실패, 현재 페이지에서 분석 시도")

        final_url = page.url
        print(f"   🔗 최종 도착: {final_url[:60]}...")

        mall_name = "기타몰"
        set_price = 0

        # 4. 가격 추출 (지마켓/옥션 정밀 타격)
        if "auction.co.kr" in final_url or "gmarket.co.kr" in final_url:
            mall_name = "옥션" if "auction" in final_url else "지마켓"
            
            # 3번째 스샷의 '59,770원' 같은 설정가를 잡기 위한 선택자
            # 지마켓 상세페이지의 '판매가' 영역을 집중 공략
            price_selectors = [
                "span.price_inner__price", # 지마켓 설정가
                "del.original-price",      # 지마켓 할인 전 가격
                "#lblSellingPrice",        # 옥션/지마켓 공통
                ".price_real", ".price_main",
                "strong.price_real_value"  # 검색결과용 대비
            ]

            for s in price_selectors:
                el = await page.query_selector(s)
                if el:
                    txt = await el.inner_text()
                    num = re.sub(r'[^0-9]', '', txt)
                    if num and int(num) > 1000: # 너무 낮은 가격(배송비 등) 제외
                        set_price = int(num)
                        print(f"   🎯 가격 발견 ({s}): {set_price}")
                        break
        
        return mall_name, set_price

    except Exception as e:
        print(f"   ⚠️ 에러: {str(e)[:50]}")
        return "에러", 0

async def main():
    creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
    creds = json.loads(creds_raw)
    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_key(SH_ID)
    
    try:
        wks = sh.worksheet("정산가분석")
    except:
        wks = sh.add_worksheet(title="정산가분석", rows="1000", cols="6")
        wks.append_row(["수집시간", "상품명", "구성", "판매처", "설정가", "정산금(85%)"])

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
                if not url: continue
                mall, price = await get_mall_set_price(page, url, f"{idx+1}개입")
                
                if price > 0:
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    settle = int(price * 0.85)
                    wks.append_row([now_str, prod_name, f"{idx+1}개입", mall, price, settle])
                    print(f"   ✅ 성공: {mall} / {price}원")
                else:
                    print(f"   ❌ 실패 ({mall})")
                
                await asyncio.sleep(random.randint(10, 15))
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
