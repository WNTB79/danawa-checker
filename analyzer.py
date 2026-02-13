import asyncio
import random
import re
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import gspread

# --- 설정 (기존 정보 유지) ---
SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ"

# 테스트를 위해 '콘드1200' 1개 상품의 6개 주소만 설정
PRODUCTS = {
    "콘드1200": [
        "https://prod.danawa.com/info/?pcode=13412984", "https://prod.danawa.com/info/?pcode=13413059",
        "https://prod.danawa.com/info/?pcode=13413086", "https://prod.danawa.com/info/?pcode=13413254",
        "https://prod.danawa.com/info/?pcode=13678937", "https://prod.danawa.com/info/?pcode=13413314"
    ]
}

async def get_mall_set_price(page, url, idx_name):
    """다나와 유료배송 1위를 클릭해 들어가서 판매자 설정가를 가져옴"""
    try:
        print(f"🔎 {idx_name} 분석 중: {url}")
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(5)
        
        # 1. 기존 로직처럼 '유료배송' 아이템 찾기
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        items = soup.select(".diff_item, .product-item, li[id^='productItem']")

        target_link_selector = None
        for i, item in enumerate(items):
            all_text = item.get_text(separator=' ', strip=True)
            # '무료배송'이 아니고 '원'이 포함된 유료배송 아이템 중 첫 번째(1위)
            if "무료배송" not in all_text and ("배송비" in all_text or "원" in all_text):
                # 해당 아이템의 클릭 가능한 링크(a 태그)의 선택자 생성
                target_link_selector = f".diff_item:nth-of-type({i+1}) .prc_c a, .diff_item:nth-of-type({i+1}) .price a"
                break

        if not target_link_selector:
            return "유료배송없음", 0

        # 2. 1위 판매처 클릭 (새 탭 열기)
        try:
            async with page.context.expect_page() as new_page_info:
                # 해당 요소를 찾아 클릭
                await page.click(target_link_selector, timeout=5000)
            mall_page = await new_page_info.value
        except:
            print("   ⚠️ 클릭 실패 또는 새 창 미발생")
            return "클릭실패", 0

        await mall_page.bring_to_front()
        await asyncio.sleep(6) # 상세페이지 로딩 대기
        
        curr_url = mall_page.url
        mall_name = "기타"
        set_price = 0

        # 3. 쇼핑몰별 '판매자 설정가' 추출
        if "auction.co.kr" in curr_url:
            mall_name = "옥션"
            el = await mall_page.query_selector("#lblSellingPrice") # 옥션 설정가 ID
            if el:
                price_text = await el.inner_text()
                set_price = int(re.sub(r'[^0-9]', '', price_text))

        elif "gmarket.co.kr" in curr_url:
            mall_name = "지마켓"
            # 지마켓은 여러 후보 중 값이 있는 것을 선택
            for s in [".price_real", "#lblSellingPrice", "span.price"]:
                el = await mall_page.query_selector(s)
                if el:
                    price_text = await el.inner_text()
                    set_price = int(re.sub(r'[^0-9]', '', price_text))
                    if set_price > 0: break
        
        await mall_page.close()
        return mall_name, set_price

    except Exception as e:
        print(f"   ⚠️ 에러: {e}")
        return "에러", 0

async def main():
    # 구글 인증
    creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
    creds = json.loads(creds_raw)
    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_key(SH_ID)
    
    # '정산가분석' 탭이 없으면 생성, 있으면 연결
    try:
        wks = sh.worksheet("정산가분석")
    except:
        wks = sh.add_worksheet(title="정산가분석", rows="100", cols="10")
        wks.append_row(["수집시간", "상품명", "구성", "판매처", "설정가", "정산금(85%)"])

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()

        for prod_name, urls in PRODUCTS.items():
            print(f"🚀 {prod_name} 분석 시작...")
            for idx, url in enumerate(urls):
                if not url: continue
                
                mall, price = await get_mall_set_price(page, url, f"{idx+1}개입")
                
                if price > 0:
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    settle_money = int(price * 0.85) # 85% 정산가 계산
                    wks.append_row([now_str, prod_name, f"{idx+1}개입", mall, price, settle_money])
                    print(f"   ✅ 성공: {mall} / 설정가 {price}원 / 정산금 {settle_money}원")
                else:
                    print(f"   ❌ 실패: {mall}")
                
                await asyncio.sleep(random.randint(3, 7))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
