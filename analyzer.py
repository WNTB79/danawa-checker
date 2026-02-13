import asyncio
import random
import re
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
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
        # 1. 다나와 페이지 접속 (친구의 기존 성공 설정값 반영)
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(8)
        await page.evaluate("window.scrollTo(0, 1500)") # 친구 코드와 동일하게 1500 스크롤
        await asyncio.sleep(4)

        # 2. BeautifulSoup으로 유료배송 1위 찾기 (친구의 오리지널 로직 이식)
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        items = soup.select(".diff_item, .product-item, li[id^='productItem']")
        
        target_link = None
        for item in items:
            all_text = item.get_text(separator=' ', strip=True)
            # 유료배송 필터링
            if "무료배송" not in all_text and ("배송비" in all_text or "원" in all_text):
                a_tag = item.select_one(".prc_c a, .price a, .btn_buy a, .pay_link a")
                if a_tag and a_tag.get('href'):
                    href = a_tag.get('href')
                    target_link = "https:" + href if href.startswith("//") else (href if href.startswith("http") else "https://prod.danawa.com" + href)
                    break

        if not target_link:
            print("   ⚠️ 유료배송 업체를 찾지 못했습니다. (목록 로딩 문제일 수 있음)")
            return "업체미발견", 0

        # 3. 판매처 이동
        print(f"   🚀 판매처 이동 중... (URL 확인용: {target_link[:50]}...)")
        await page.goto(target_link, wait_until="load", timeout=60000)
        await asyncio.sleep(10) # 경유 페이지 통과를 위해 충분히 대기
        
        final_url = page.url
        print(f"   🔗 최종 도착지: {final_url[:70]}...")

        # 4. 가격 추출 (옥션/지마켓 우선 처리)
        mall_name = "기타몰"
        set_price = 0

        if "auction.co.kr" in final_url or "gmarket.co.kr" in final_url:
            mall_name = "옥션" if "auction" in final_url else "지마켓"
            # 옥션/지마켓의 '판매자 설정가' 태그들
            selectors = ["#lblSellingPrice", ".price_real", ".price_main", "span.price"]
            for s in selectors:
                el = await page.query_selector(s)
                if el:
                    txt = await el.inner_text()
                    num = re.sub(r'[^0-9]', '', txt)
                    if num:
                        set_price = int(num)
                        break
        else:
            # 옥션/지마켓이 아닐 경우 일반 가격이라도 시도
            mall_name = final_url.split('.')[1] if '.' in final_url else "기타"
            el = await page.query_selector(".price, .total_price, .prc_c")
            if el:
                txt = await el.inner_text()
                num = re.sub(r'[^0-9]', '', txt)
                set_price = int(num) if num else 0

        return mall_name, set_price

    except Exception as e:
        print(f"   ⚠️ 에러 발생: {e}")
        return "에러", 0

async def main():
    # 구글 인증 및 시트 연결
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
        # 실제 브라우저처럼 보이게 하기 위한 설정
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for prod_name, urls in PRODUCTS.items():
            print(f"--- {prod_name} 수집 시작 ---")
            for idx, url in enumerate(urls):
                if not url: continue
                
                mall, price = await get_mall_set_price(page, url, f"{idx+1}개입")
                
                if price > 0:
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    settle = int(price * 0.85)
                    wks.append_row([now_str, prod_name, f"{idx+1}개입", mall, price, settle])
                    print(f"   ✅ 성공: {mall} / {price}원 (정산가: {settle}원)")
                else:
                    print(f"   ❌ 실패: {mall}에서 가격을 찾지 못함")
                
                await asyncio.sleep(random.randint(5, 8))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
