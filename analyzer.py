import asyncio
import random
import re
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright
import gspread

# --- 설정 (친구의 시트 ID 유지) ---
SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ"

PRODUCTS = {
    "콘드1200": [
        "https://prod.danawa.com/info/?pcode=13412984", "https://prod.danawa.com/info/?pcode=13413059",
        "https://prod.danawa.com/info/?pcode=13413086", "https://prod.danawa.com/info/?pcode=13413254",
        "https://prod.danawa.com/info/?pcode=13678937", "https://prod.danawa.com/info/?pcode=13413314"
    ]
}

async def get_mall_set_price(page, url, idx_name):
    """다나와 유료배송 1위의 주소를 따서 판매자 설정가를 가져옴"""
    try:
        print(f"🔎 {idx_name} 분석 중: {url}")
        # 1. 페이지 접속 및 충분한 대기 (친구의 기존 로직 반영)
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(7)
        await page.evaluate("window.scrollTo(0, 1200)") # 리스트 로드를 위해 스크롤
        await asyncio.sleep(3)

        # 2. 유료배송 1위 링크 찾기 (친구의 기존 필터링 로직 Playwright 버전)
        # 모든 상품 아이템 추출
        items = await page.query_selector_all(".diff_item, .product-item, li[id^='productItem']")
        
        target_link = None
        for item in items:
            inner_text = await item.inner_text()
            # 친구가 사용하던 '유료배송' 판별 조건
            if "무료배송" not in inner_text and ("배송비" in inner_text or "원" in inner_text):
                # 해당 아이템 내의 클릭 가능한 링크(a 태그) 추출
                a_tag = await item.query_selector(".prc_c a, .price a, .btn_buy a")
                if a_tag:
                    href = await a_tag.get_attribute("href")
                    if href:
                        # 주소 보정 (상대 경로일 경우)
                        if href.startswith('//'): target_link = "https:" + href
                        elif href.startswith('/'): target_link = "https://prod.danawa.com" + href
                        else: target_link = href
                        break

        if not target_link:
            return "유료배송없음", 0

        # 3. 판매처로 점프 (현재 창에서 바로 이동)
        print(f"   🚀 판매처 이동 중...")
        await page.goto(target_link, wait_until="load", timeout=60000)
        await asyncio.sleep(8) # 경유 페이지 통과 대기
        
        final_url = page.url
        print(f"   🔗 최종 주소: {final_url}")
        
        mall_name = "옥션/지마켓 아님"
        set_price = 0

        # 4. 옥션/지마켓 설정가 정밀 타격
        if "auction.co.kr" in final_url or "gmarket.co.kr" in final_url:
            mall_name = "옥션" if "auction" in final_url else "지마켓"
            # 판매자가 입력한 '설정가' 태그 (할인 전 가격)
            for s in ["#lblSellingPrice", ".price_real", ".price_main", ".un-tr-price"]:
                el = await page.query_selector(s)
                if el:
                    txt = await el.inner_text()
                    set_price = int(re.sub(r'[^0-9]', '', txt))
                    if set_price > 0: break
        
        return mall_name, set_price

    except Exception as e:
        print(f"   ⚠️ 에러: {str(e)[:50]}...")
        return "오류", 0

async def main():
    # 시트/인증 설정
    creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
    creds = json.loads(creds_raw)
    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_key(SH_ID)
    
    try:
        wks = sh.worksheet("정산가분석")
    except:
        wks = sh.add_worksheet(title="정산가분석", rows="100", cols="6")
        wks.append_row(["수집시간", "상품명", "구성", "판매처", "설정가", "정산금(85%)"])

    async with async_playwright() as p:
        # 사람처럼 보이게 세팅
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for prod_name, urls in PRODUCTS.items():
            for idx, url in enumerate(urls):
                if not url: continue
                
                mall, price = await get_mall_set_price(page, url, f"{idx+1}개입")
                
                if price > 0:
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    settle = int(price * 0.85)
                    wks.append_row([now_str, prod_name, f"{idx+1}개입", mall, price, settle])
                    print(f"   ✅ 수집성공: {mall} / {price}원")
                else:
                    print(f"   ❌ 데이터 없음 (추출불가 또는 타몰)")
                
                await asyncio.sleep(random.randint(5, 10))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
