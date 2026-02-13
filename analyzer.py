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
    "콘드1200": [
        "https://prod.danawa.com/info/?pcode=13412984", "https://prod.danawa.com/info/?pcode=13413059",
        "https://prod.danawa.com/info/?pcode=13413086", "https://prod.danawa.com/info/?pcode=13413254",
        "https://prod.danawa.com/info/?pcode=13678937", "https://prod.danawa.com/info/?pcode=13413314"
}

async def get_seller_price(page, url):
    """다나와 1위 상품의 상세페이지로 들어가서 판매자 설정가를 가져오는 함수"""
    try:
        # 페이지 접속 시 충분한 시간을 줍니다
        await page.goto(url, wait_until="networkidle") 
        await asyncio.sleep(3) 

        # 1. 다나와 리스트에서 1위 판매처 찾기 (광고 제외하고 가장 첫 번째)
        # 다양한 레이아웃(리스트형, 카드형)에 대응하기 위한 여러 선택자 시도
        first_seller = None
        selectors = [
            ".product_list .product_item:not(.product_ad_item) .grid_main_info .price_sect a",
            ".diff_item:not(.ad_item) .diff_item_price a",
            ".rank_one:not(.ad_item) .price_line a"
        ]
        
        for selector in selectors:
            first_seller = await page.query_selector(selector)
            if first_seller:
                break

        if not first_seller:
            print("❌ 다나와 리스트에서 가격 링크를 찾지 못했습니다.")
            return "N/A", 0

        # 클릭해서 새 탭(상세페이지) 열기
        async with page.context.expect_page() as new_page_info:
            await first_seller.click()
        
        target_page = await new_page_info.value
        await target_page.bring_to_front()
        # 상세페이지 로딩 대기
        await asyncio.sleep(5) 

        current_url = target_page.url
        print(f"🔗 이동된 판매처: {current_url}")

        price = 0
        seller_name = "알 수 없음"

        # 2. 플랫폼별 설정가 추출 로직 (옥션/지마켓 우선)
        if "auction.co.kr" in current_url:
            seller_name = "옥션"
            element = await target_page.query_selector("#lblSellingPrice")
            if element:
                price_text = await element.inner_text()
                price = int(re.sub(r'[^0-9]', '', price_text))
        
        elif "gmarket.co.kr" in current_url:
            seller_name = "지마켓"
            # 지마켓의 다양한 가격 태그 시도
            for s in [".price_real", "#lblSellingPrice", ".un-tr-price"]:
                element = await target_page.query_selector(s)
                if element:
                    price_text = await element.inner_text()
                    if price_text.strip():
                        price = int(re.sub(r'[^0-9]', '', price_text))
                        break
        
        else:
            seller_name = "기타(확인필요)"
            # 일반적인 쇼핑몰 가격 태그 시도
            for s in [".price", ".total_price", ".pay-amount"]:
                element = await target_page.query_selector(s)
                if element:
                    price_text = await element.inner_text()
                    price = int(re.sub(r'[^0-9]', '', price_text))
                    break

        await target_page.close()
        return seller_name, price  # <--- 여기까지가 수정할 부분의 끝입니다!

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
