import asyncio
import re
import json
import os
import random
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

async def get_price_final(page, url, idx_name):
    try:
        print(f"🔎 {idx_name} 분석: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        # 1. 다나와 '최저가 구매하기' 버튼 클릭 (링크 추출 대신 직접 클릭)
        try:
            buy_btn = await page.get_by_role("link", name=re.compile("최저가 구매하기|구매하기")).first
            if await buy_btn.is_visible():
                print("   🎯 최저가 구매 버튼 클릭!")
                await buy_btn.click()
            else:
                # 버튼이 안 보이면 두 번째 방법 (셀렉터)
                await page.click(".lowest_area a.item__link", timeout=5000)
        except:
            print("   ❌ 버튼 클릭 실패, 일반 분석 시도")

        await asyncio.sleep(10) # 쇼핑몰 이동 대기

        # 2. 지마켓 검색 페이지에 머물러 있는지 확인 후 첫 상품 클릭
        if "gmarket.co.kr/n/search" in page.url or "keyword=" in page.url:
            print("   ⚠️ 검색 리스트 발견! 첫 번째 상품 강제 클릭...")
            try:
                # 검색 결과의 첫 번째 상품 썸네일 혹은 제목 클릭
                first_item = await page.locator(".box__item-container a, .image__item, .link__item").first
                await first_item.click()
                await asyncio.sleep(8)
            except:
                print("   ❌ 검색결과 클릭 실패")

        # 3. 상세페이지 보안 회피 (스크롤링)
        print(f"   🔗 최종 페이지 도달: {page.url[:50]}...")
        await page.mouse.wheel(0, 500) # 살짝 내림
        await asyncio.sleep(2)
        await page.mouse.wheel(0, -200) # 살짝 올림
        await asyncio.sleep(3)

        # 4. 설정가(원가) 추출
        mall_name = "지마켓" if "gmarket" in page.url else "옥션" if "auction" in page.url else "기타"
        price = 0
        
        # 지마켓/옥션 상세페이지의 다양한 가격 태그 집중 공략
        selectors = [
            "span.price_inner__price", "del.original-price", 
            "#lblSellingPrice", "strong.price_real_value", ".price_real",
            ".price_main span", "div.price_area"
        ]

        for s in selectors:
            try:
                el = await page.query_selector(s)
                if el:
                    txt = await el.inner_text()
                    num = int(re.sub(r'[^0-9]', '', txt))
                    if 10000 < num < 1000000: # 정상적인 가격 범위 체크
                        price = num
                        print(f"   💰 가격 발견: {price}원 ({mall_name})")
                        return mall_name, price
            except: continue
            
        return mall_name, 0

    except Exception as e:
        print(f"   ⚠️ 오류: {str(e)[:100]}")
        return None, 0

async def main():
    creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
    creds = json.loads(creds_raw)
    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_key(SH_ID)
    wks = sh.worksheet("정산가분석")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 봇 탐지 방지를 위한 실제 브라우저 환경 설정
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for prod_name, urls in PRODUCTS.items():
            print(f"\n--- {prod_name} 분석 시작 ---")
            for idx, url in enumerate(urls):
                mall, price = await get_price_final(page, url, f"{idx+1}개입")
                if price > 0:
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    wks.append_row([now, prod_name, f"{idx+1}개입", mall, price, int(price * 0.85)])
                    print("   ✅ 시트 업데이트 완료")
                else:
                    print("   ❌ 수집 실패 (가격 못 찾음)")
                
                await asyncio.sleep(random.randint(10, 15))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
