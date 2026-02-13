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

async def get_price_final(browser_context, url, idx_name):
    page = await browser_context.new_page()
    try:
        print(f"🔎 {idx_name} 분석: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.mouse.wheel(0, 500)
        await asyncio.sleep(3)

        async with page.expect_popup() as popup_info:
            print("   🎯 최저가 구매 버튼 클릭!")
            try:
                btn = page.get_by_text("최저가 구매하기").first
                await btn.click(timeout=15000)
            except:
                await page.click(".lowest_area a.item__link, .lowest_list .item__link a", timeout=15000)
        
        new_page = await popup_info.value
        await new_page.bring_to_front()
        
        # 지마켓/옥션/11번가 공통: 페이지 완전 로딩 대기
        await asyncio.sleep(15) 

        # 지마켓 검색 리스트에서 상세페이지로 한 번 더 진입
        if "search" in new_page.url or "keyword=" in new_page.url:
            print("   🖱️ 검색 리스트에서 실제 상품 클릭 중...")
            try:
                # 지마켓/옥션 리스트의 첫 번째 상품
                await new_page.locator(".box__item-container a, .image__item, .link__item").first.click(timeout=10000)
                await asyncio.sleep(10) # 상세페이지 로딩 대기
            except: pass

        print(f"   🔗 최종 페이지: {new_page.url[:60]}")
        
        mall_name = "지마켓" if "gmarket" in new_page.url else "옥션" if "auction" in new_page.url else "11번가" if "11st" in new_page.url else "기타"
        price = 0
        
        # [핵심] 설정가(원가)를 찾기 위한 더 강력한 선택자들
        # 지마켓 원가(price_inner__price), 11번가 원가(price_detail), 일반적인 원가 태그들
        selectors = [
            "span.price_inner__price", 
            "del.original-price", 
            "#lblSellingPrice", 
            ".price_detail .value", 
            ".price_real", 
            "strong.price_real_value",
            "span[class*='original']",
            "span[class*='price_main']"
        ]
        
        for s in selectors:
            try:
                el = await new_page.query_selector(s)
                if el:
                    txt = await el.inner_text()
                    # 숫자만 추출
                    num = int(re.sub(r'[^0-9]', '', txt))
                    if num > 10000: # 배송비 등 제외를 위해 1만원 이상만 취급
                        price = num
                        print(f"   💰 가격 발견: {price}원 ({mall_name})")
                        break
            except: continue
            
        await new_page.close()
        return mall_name, price

    except Exception as e:
        print(f"   ⚠️ 오류: {str(e)[:100]}")
        return None, 0
    finally:
        await page.close()

async def main():
    # 시트 연결 확인
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

        for prod_name, urls in PRODUCTS.items():
            print(f"\n--- {prod_name} 수집 시작 ---")
            for idx, url in enumerate(urls):
                mall, price = await get_price_final(context, url, f"{idx+1}개입")
                
                # 가격이 0보다 클 때만 무조건 기록! (기록 로그 추가)
                if price > 0:
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    row_data = [now, prod_name, f"{idx+1}개입", mall, price, int(price * 0.85)]
                    wks.append_row(row_data)
                    print(f"   ✅ 시트 기록 성공: {row_data}")
                else:
                    print(f"   ❌ 가격을 찾지 못해 기록을 건너뜁니다.")
                
                await asyncio.sleep(random.randint(10, 15))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
