import asyncio
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

async def get_price_simple(page, url, idx_name):
    try:
        print(f"🔎 {idx_name} 시작: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(4)

        # [전략 1] 상단에 있는 가장 큰 '최저가 구매' 버튼 링크 추출
        # 다나와 상단 최저가 영역의 a 태그를 타겟팅
        target_link = await page.evaluate("""() => {
            const topPriceArea = document.querySelector('.lowest_area .lowest_list .item__link a');
            return topPriceArea ? topPriceArea.href : null;
        }""")

        if not target_link:
            # 상단 버튼이 없을 경우 대비 (일반 리스트의 첫 번째)
            target_link = await page.evaluate("() => { const a = document.querySelector('.prc_c a'); return a ? a.href : null; }")

        if not target_link:
            print(f"   ❌ 링크 못 찾음")
            return None, 0

        # 쇼핑몰 이동
        print(f"   🚀 1위 판매처로 이동...")
        await page.goto(target_link, wait_until="load", timeout=90000)
        await asyncio.sleep(8)

        # [전략 2] 지마켓/옥션 검색 리스트면 첫 번째 상품 클릭
        if "search" in page.url or "Search" in page.url:
            try:
                await page.click(".box__item-container a, .image__item, #item_img_0", timeout=5000)
                await asyncio.sleep(6)
            except: pass

        final_url = page.url
        print(f"   🔗 도착: {final_url[:60]}")

        # 지마켓/옥션인지 확인
        mall_name = ""
        if "gmarket" in final_url: mall_name = "지마켓"
        elif "auction" in final_url: mall_name = "옥션"
        else:
            print(f"   ⚠️ 지마켓/옥션 아님 ({final_url.split('.')[1]}) - 건너뜁니다.")
            return None, 0

        # [전략 3] 설정가(할인 전 가격) 추출
        # 스샷에서 확인된 '59,770원' 같은 가격을 잡는 가장 확실한 선택자들
        price = 0
        price_selectors = [
            "span.price_inner__price", # 지마켓 설정가
            "del.original-price",      # 지마켓 할인 전
            "#lblSellingPrice",        # 옥션 설정가
            ".price_real", "strong.price_real_value"
        ]

        for s in price_selectors:
            el = await page.query_selector(s)
            if el:
                txt = await el.inner_text()
                num = int(re.sub(r'[^0-9]', '', txt))
                if num > 1000:
                    price = num
                    print(f"   🎯 {mall_name} 가격 발견: {price}원")
                    break
        
        return mall_name, price

    except Exception as e:
        print(f"   ⚠️ 에러: {str(e)[:50]}")
        return None, 0

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
            print(f"\n--- {prod_name} 수집 ---")
            for idx, url in enumerate(urls):
                mall, price = await get_price_simple(page, url, f"{idx+1}개입")
                if mall and price > 0:
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    wks.append_row([now, prod_name, f"{idx+1}개입", mall, price, int(price*0.85)])
                    print(f"   ✅ 시트 기록 완료")
                await asyncio.sleep(10)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
