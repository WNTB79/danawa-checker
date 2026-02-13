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
        
        # 1. 다나와 페이지 접속
        await page.goto(url, wait_until="load", timeout=60000)
        
        # 2. 가격 비교 리스트가 나타날 때까지 대기
        try:
            # .diff_item (일반 리스트) 또는 .product-pot (오른쪽 섹션 관련) 대기
            await page.wait_for_selector(".diff_item, .prc_line", timeout=20000)
            print("   ✅ 가격 리스트 로드 완료")
        except:
            print("   ⚠️ 리스트 로딩 지연 중...")

        await asyncio.sleep(5)
        # 오른쪽 섹션과 하단 리스트가 모두 나오도록 넉넉히 스크롤
        await page.evaluate("window.scrollTo(0, 1500)") 
        await asyncio.sleep(3)

        # 3. BeautifulSoup으로 정밀 분석
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        
        # 다나와의 모든 판매 아이템 행을 수집
        items = soup.select(".diff_item, [id^='productItem']")
        
        target_link = None
        found_mall_count = 0

        for item in items:
            # 배송비 정보가 들어있는 영역을 특정해서 추출 (.ship, .delivery 등)
            ship_info = item.select_one(".ship, .delivery, .deliv")
            ship_text = ship_info.get_text(strip=True) if ship_info else ""
            
            # 전체 텍스트 추출
            all_text = item.get_text(separator=' ', strip=True)
            
            # [조건] 1. '무료배송'이라는 단어가 없어야 함
            #        2. '배송비'라는 단어가 있거나, 숫자로 된 배송비가 보여야 함
            is_free = "무료배송" in all_text or "무료" in ship_text
            has_shipping_fee = "배송비" in all_text or any(char.isdigit() for char in ship_text)

            if not is_free and has_shipping_fee:
                # 유료배송 업체 발견! 링크 추출
                a_tag = item.select_one(".prc_c a, .price a, .btn_buy a, a.p_link")
                if a_tag and a_tag.get('href'):
                    href = a_tag.get('href')
                    if href.startswith("//"): target_link = "https:" + href
                    elif href.startswith("/"): target_link = "https://prod.danawa.com" + href
                    else: target_link = href
                    found_mall_count += 1
                    break # 1위만 찾으면 되므로 탈출

        if not target_link:
            # 만약 위 조건으로 못찾았다면, 리스트의 가장 첫 번째 아이템이라도 시도 (예외 처리)
            if items:
                first_item = items[0]
                a_tag = first_item.select_one(".prc_c a, .price a, .btn_buy a")
                if a_tag and a_tag.get('href'):
                    href = a_tag.get('href')
                    target_link = "https:" + href if href.startswith("//") else href
                    print("   ⚠️ 유료배송 필터 실패로 1순위 업체 강제 선택")

        if not target_link:
            print(f"   ❌ {idx_name}: 링크 추출 실패")
            return "업체미발견", 0

        # 4. 판매처 이동
        print(f"   🚀 판매처 이동 중...")
        await page.goto(target_link, wait_until="load", timeout=60000)
        await asyncio.sleep(12) # 쇼핑몰 로딩 및 경유 대기
        
        final_url = page.url
        print(f"   🔗 최종 도착: {final_url[:70]}...")

        mall_name = "기타몰"
        set_price = 0

        # 5. 판매자 설정가 추출 (옥션/지마켓 정밀 타격)
        if "auction.co.kr" in final_url or "gmarket.co.kr" in final_url:
            mall_name = "옥션" if "auction" in final_url else "지마켓"
            # 옥션/지마켓의 할인 전 '판매가' 태그들
            selectors = ["#lblSellingPrice", ".price_real", ".price_main", "span.price", ".un-tr-price"]
            for s in selectors:
                el = await page.query_selector(s)
                if el:
                    txt = await el.inner_text()
                    num = re.sub(r'[^0-9]', '', txt)
                    if num:
                        set_price = int(num)
                        break
        else:
            # 옥션/지마켓이 아닐 경우 일반 가격 추출 시도
            el = await page.query_selector(".price, .total_price, .prc_c")
            if el:
                txt = await el.inner_text()
                num = re.sub(r'[^0-9]', '', txt)
                set_price = int(num) if num else 0
        
        return mall_name, set_price

    except Exception as e:
        print(f"   ⚠️ 에러: {str(e)[:50]}")
        return "에러", 0

async def main():
    # 시트 인증
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
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for prod_name, urls in PRODUCTS.items():
            print(f"\n--- {prod_name} 수집 시작 ---")
            for idx, url in enumerate(urls):
                if not url or url == "": continue
                
                mall, price = await get_mall_set_price(page, url, f"{idx+1}개입")
                
                if price > 0:
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    settle = int(price * 0.85)
                    wks.append_row([now_str, prod_name, f"{idx+1}개입", mall, price, settle])
                    print(f"   ✅ 성공: {mall} / {price}원")
                else:
                    print(f"   ❌ 실패 ({mall})")
                
                await asyncio.sleep(random.randint(5, 10))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
