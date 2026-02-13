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
    """다나와 유료배송 1위의 링크를 직접 추출해서 이동 후 판매자 설정가를 가져옴"""
    try:
        print(f"🔎 {idx_name} 분석 중: {url}")
        # 1. 다나와 상세페이지 접속
        await page.goto(url, wait_until="load", timeout=60000)
        await asyncio.sleep(5)
        
        # 스크롤을 내려서 가격 비교표가 완전히 로드되게 함
        await page.evaluate("window.scrollTo(0, 800)")
        await asyncio.sleep(2)

        # 2. HTML 분석해서 유료배송 1위 링크 따오기
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        
        # 다나와 가격비교 목록 아이템들
        items = soup.select(".diff_item, [id^='productItem']")
        
        final_link = None
        for item in items:
            all_text = item.get_text(separator=' ', strip=True)
            # '무료배송'이 아닌 항목 중 첫 번째
            if "무료배송" not in all_text and ("배송비" in all_text or "원" in all_text):
                a_tag = item.select_one(".prc_c a, .price a, .btn_buy a")
                if a_tag and a_tag.get('href'):
                    # 다나와 내부 링크인 경우 도메인 붙여주기
                    link = a_tag.get('href')
                    if link.startswith('//'):
                        final_link = "https:" + link
                    elif link.startswith('/'):
                        final_link = "https://prod.danawa.com" + link
                    else:
                        final_link = link
                    break

        if not final_link:
            print("   ⚠️ 유료배송 1위 링크를 찾지 못했습니다.")
            return "링크미발견", 0

        # 3. 추출한 링크로 직접 이동 (새 탭 대신 현재 탭 사용으로 안정성 확보)
        print(f"   🚀 판매처로 이동 중...")
        await page.goto(final_link, wait_until="load", timeout=60000)
        
        # 경유 페이지(v_gate) 등 대기시간 포함
        await asyncio.sleep(8)
        
        curr_url = page.url
        print(f"   🔗 최종 도착지: {curr_url}")
        
        mall_name = "기타"
        set_price = 0

        # 4. 쇼핑몰별 '판매자 설정가' 추출 (옥션/지마켓)
        if "auction.co.kr" in curr_url:
            mall_name = "옥션"
            # 여러 태그 후보군 탐색
            for s in ["#lblSellingPrice", ".price_real", ".price_inner .price"]:
                el = await page.query_selector(s)
                if el:
                    price_text = await el.inner_text()
                    set_price = int(re.sub(r'[^0-9]', '', price_text))
                    if set_price > 0: break

        elif "gmarket.co.kr" in curr_url:
            mall_name = "지마켓"
            for s in [".price_real", "#lblSellingPrice", "span.price", ".price_main"]:
                el = await page.query_selector(s)
                if el:
                    price_text = await el.inner_text()
                    set_price = int(re.sub(r'[^0-9]', '', price_text))
                    if set_price > 0: break
        
        return mall_name, set_price

    except Exception as e:
        print(f"   ⚠️ 함수 내 에러: {e}")
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
