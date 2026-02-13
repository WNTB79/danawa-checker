import os
import json
import asyncio
import random
import gspread
import re
from datetime import datetime
from playwright.async_api import async_playwright

# --- 설정 (기존 정보 활용) ---
SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ"  # 친구의 시트 ID
# 분석할 상품 리스트 (기존 PRODUCTS와 동일하게 유지하거나 테스트용으로 몇 개만 두셔도 됩니다)
# 우선은 옥션/지마켓 비중이 높은 상품 위주로 테스트해보세요.
PRODUCTS = {
    "비타민": ["https://search.danawa.com/dsearch.php?query=비타민C"],
    "오메가3": ["https://search.danawa.com/dsearch.php?query=오메가3"]
}

async def get_seller_price(page, url):
    """다나와 1위 상품의 상세페이지로 들어가서 판매자 설정가를 가져오는 함수"""
    try:
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2) # 로딩 대기

        # 1. 다나와 리스트에서 1위 판매처 클릭 (최저가 업체 링크)
        # 광고 상품을 제외한 실제 1위 판매처의 '구매하기' 혹은 '판매처 이동' 버튼을 찾습니다.
        first_seller_selector = ".diff_item:not(.ad_item) .diff_item_price a"
        first_seller = await page.query_selector(first_seller_selector)
        
        if not first_seller:
            print("❌ 1위 판매처를 찾을 수 없습니다.")
            return "N/A", 0

        # 새 창이 뜨는 경우가 많으므로 context를 통해 추적합니다.
        async with page.context.expect_page() as new_page_info:
            await first_seller.click()
        
        target_page = await new_page_info.value
        await target_page.bring_to_front()
        await asyncio.sleep(3) # 상세페이지 로딩 대기

        current_url = target_page.url
        print(f"🔗 이동된 판매처: {current_url}")

        price = 0
        seller_name = "알 수 없음"

        # 2. 플랫폼별 설정가 추출 로직 (옥션/지마켓 우선)
        if "auction.co.kr" in current_url:
            seller_name = "옥션"
            # 옥션 설정가 태그 (일반적인 id)
            element = await target_page.query_selector("#lblSellingPrice")
            if element:
                price_text = await element.inner_text()
                price = int(re.sub(r'[^0-9]', '', price_text))
        
        elif "gmarket.co.kr" in current_url:
            seller_name = "지마켓"
            # 지마켓 설정가 태그
            element = await target_page.query_selector(".price_real")
            if not element:
                element = await target_page.query_selector("#lblSellingPrice")
            if element:
                price_text = await element.inner_text()
                price = int(re.sub(r'[^0-9]', '', price_text))
        
        else:
            seller_name = "기타(분석필요)"
            # 기타 사이트는 일반적인 가격 태그 시도
            element = await target_page.query_selector(".price")
            if element:
                price_text = await element.inner_text()
                price = int(re.sub(r'[^0-9]', '', price_text))

        await target_page.close()
        return seller_name, price

    except Exception as e:
        print(f"⚠️ 상세페이지 분석 오류: {e}")
        return "오류", 0

async def main():
    creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
    creds = json.loads(creds_raw)
    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_key(SH_ID)
    wks = sh.worksheet("정산가분석") # 새로 만든 탭 이름

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for tab_name, urls in PRODUCTS.items():
            for url in urls:
                print(f"🔍 {tab_name} 1위 추적 시작...")
                seller, price = await get_seller_price(page, url)
                
                if price > 0:
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    settle_price = int(price * 0.85) # 85% 정산가 계산
                    
                    # 시트에 기록 [시간, 상품군, 업체명, 설정가, 85%정산가]
                    wks.append_row([now_str, tab_name, seller, price, settle_price])
                    print(f"✅ {tab_name} 기록 완료: {price}원 -> 정산가 {settle_price}원")
                
                await asyncio.sleep(random.randint(2, 5))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
