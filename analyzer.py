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
    # 메인 페이지 생성
    page = await browser_context.new_page()
    try:
        print(f"🔎 {idx_name} 분석: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        # [핵심] 클릭 시 새로 열리는 탭(팝업)을 기다림
        async with page.expect_popup() as popup_info:
            print("   🎯 최저가 구매 버튼 클릭 시도...")
            # 가장 확실한 셀렉터로 클릭
            await page.click(".lowest_area a.item__link, .lowest_list .item__link a", timeout=10000)
        
        # 새로 열린 쇼핑몰 페이지로 제어권 전환
        new_page = await popup_info.value
        await new_page.bring_to_front()
        print("   🚀 쇼핑몰 새 탭으로 이동 성공!")
        
        await asyncio.sleep(10) # 쇼핑몰 로딩 대기

        # 지마켓 검색 리스트 대응
        if "gmarket.co.kr/n/search" in new_page.url:
            print("   ⚠️ 검색 리스트 발견! 첫 상품 클릭...")
            try:
                await new_page.click(".box__item-container a, .image__item", timeout=10000)
                await asyncio.sleep(8)
            except: pass

        print(f"   🔗 최종 주소 확인: {new_page.url[:60]}")
        
        # 가격 추출
        mall_name = "지마켓" if "gmarket" in new_page.url else "옥션" if "auction" in new_page.url else "기타"
        price = 0
        
        # 설정가(원가) 타겟팅
        selectors = ["span.price_inner__price", "del.original-price", "#lblSellingPrice", ".price_real"]
        
        for s in selectors:
            try:
                el = await new_page.query_selector(s)
                if el:
                    txt = await el.inner_text()
                    num = int(re.sub(r'[^0-9]', '', txt))
                    if num > 10000:
                        price = num
                        print(f"   💰 가격 발견: {price}원 ({mall_name})")
                        break
            except: continue
            
        await new_page.close()
        return mall_name, price

    except Exception as e:
        print(f"   ⚠️ 오류: {str(e)[:50]}")
        return None, 0
    finally:
        await page.close()

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

        for prod_name, urls in PRODUCTS.items():
            print(f"\n--- {prod_name} 분석 시작 ---")
            for idx, url in enumerate(urls):
                mall, price = await get_price_final(context, url, f"{idx+1}개입")
                if price > 0:
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    wks.append_row([now, prod_name, f"{idx+1}개입", mall, price, int(price * 0.85)])
                    print("   ✅ 기록 완료")
                
                await asyncio.sleep(random.randint(5, 10))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
