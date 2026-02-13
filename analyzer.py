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
        # 봇 탐지 방지를 위해 대기 시간을 조절하고 데스크탑 뷰로 강제 고정해
        await page.goto(url, wait_until="load", timeout=60000)
        
        # 2. 가격 비교 리스트가 나타날 때까지 '확실히' 대기 (핵심!)
        # .diff_item이나 #productPriceComparison 요소가 뜰 때까지 기다림
        try:
            await page.wait_for_selector(".diff_item, .low_lst", timeout=20000)
            print("   ✅ 가격 리스트 로드 완료")
        except:
            print("   ⚠️ 리스트 로딩 시간이 길어지고 있습니다. 계속 진행해봅니다.")

        await asyncio.sleep(5)
        await page.evaluate("window.scrollTo(0, 1500)") 
        await asyncio.sleep(3)

        # 3. BeautifulSoup으로 유료배송 1위 찾기 (친구의 기존 로직 강화)
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        
        # 다나와 상세페이지의 다양한 아이템 선택자 대응
        items = soup.select(".diff_item, [id^='productItem'], .product-item")
        
        target_link = None
        for item in items:
            all_text = item.get_text(separator=' ', strip=True)
            # 친구의 필터링 조건: 유료배송만 찾기
            if "무료배송" not in all_text and ("배송비" in all_text or "원" in all_text):
                # 클릭할 수 있는 모든 가능한 태그를 뒤져서 href 추출
                a_tag = item.select_one(".prc_c a, .price a, .btn_buy a, .pay_link a, a.p_link")
                if a_tag and a_tag.get('href'):
                    href = a_tag.get('href')
                    # 주소 형식 보정
                    if href.startswith("//"): target_link = "https:" + href
                    elif href.startswith("/"): target_link = "https://prod.danawa.com" + href
                    else: target_link = href
                    break

        if not target_link:
            # 실패 시 로그를 더 자세히 남겨서 분석할 수 있게 함
            print(f"   ❌ {idx_name}: 유료배송 1위 업체를 찾지 못함 (발견된 아이템 수: {len(items)})")
            return "업체미발견", 0

        # 4. 판매처로 이동
        print(f"   🚀 판매처 이동: {target_link[:60]}...")
        await page.goto(target_link, wait_until="load", timeout=60000)
        
        # 경유 페이지(v_gate) 등 통과를 위해 충분히 대기
        await asyncio.sleep(12) 
        
        final_url = page.url
        print(f"   🔗 최종 도착: {final_url[:70]}...")

        mall_name = "기타몰"
        set_price = 0

        # 5. 가격 추출 (옥션/지마켓 정밀 타격)
        if "auction.co.kr" in final_url or "gmarket.co.kr" in final_url:
            mall_name = "옥션" if "auction" in final_url else "지마켓"
            # 판매자 설정가(할인 전 가격)를 찾기 위한 태그들
            selectors = ["#lblSellingPrice", ".price_real", ".price_main", "span.price", ".un-tr-price"]
            for s in selectors:
                el = await page.query_selector(s)
                if el:
                    txt = await el.inner_text()
                    num = re.sub(r'[^0-9]', '', txt)
                    if num:
                        set_price = int(num)
                        break
        
        return mall_name, set_price

    except Exception as e:
        print(f"   ⚠️ 실행 중 에러: {str(e)[:100]}")
        return "에러", 0

async def main():
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
        # 중요: 실제 사람 브라우저처럼 보이게 창 크기와 정보 설정
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for prod_name, urls in PRODUCTS.items():
            print(f"\n--- {prod_name} 수집 시작 ---")
            for idx, url in enumerate(urls):
                if not url: continue
                
                mall, price = await get_mall_set_price(page, url, f"{idx+1}개입")
                
                if price > 0:
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    settle = int(price * 0.85)
                    wks.append_row([now_str, prod_name, f"{idx+1}개입", mall, price, settle])
                    print(f"   ✅ 수집성공: {mall} / {price}원")
                else:
                    print(f"   ❌ 수집실패 ({mall})")
                
                # 다음 페이지 분석 전 휴식
                await asyncio.sleep(random.randint(7, 12))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
