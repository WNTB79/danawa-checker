import asyncio
import random
import re
import json
import os
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

async def get_mall_set_price(page, url, idx_name):
    try:
        print(f"🔎 {idx_name} 분석 시작: {url}")
        
        # 1. 다나와 페이지 접속
        await page.goto(url, wait_until="load", timeout=60000)
        
        # 2. 가격 비교 리스트 로딩 대기
        try:
            await page.wait_for_selector(".diff_item, .prc_line", timeout=20000)
            print("   ✅ 리스트 로드 확인")
        except:
            print("   ⚠️ 리스트 로딩 지연...")

        await asyncio.sleep(4)
        await page.evaluate("window.scrollTo(0, 1000)")
        await asyncio.sleep(2)

        # 3. 유료배송 1위 링크 추출 (가장 정확한 판매처 이동 링크 찾기)
        # 광고 상품을 제외하고 실제 가격 비교 테이블(.diff_item)에서 추출
        items = await page.query_selector_all(".diff_item")
        
        target_link = None
        for item in items:
            inner_text = await item.inner_text()
            # 유료배송 필터 (무료배송 제외)
            if "무료" not in inner_text and ("배송비" in inner_text or "원" in inner_text):
                # 판매처로 이동하는 '구매' 버튼이나 '몰 로고' 링크 추출
                a_tag = await item.query_selector(".prc_c a, .mall_nm a, .btn_buy a")
                if a_tag:
                    href = await a_tag.get_attribute("href")
                    if href and "javascript" not in href:
                        target_link = "https:" + href if href.startswith("//") else (href if href.startswith("http") else "https://prod.danawa.com" + href)
                        break

        if not target_link:
            print(f"   ❌ {idx_name}: 링크 추출 실패")
            return "업체미발견", 0

        # 4. 쇼핑몰 이동
        print(f"   🚀 판매처 이동: {target_link[:50]}...")
        await page.goto(target_link, wait_until="load", timeout=90000)
        await asyncio.sleep(12) # 경유 페이지 및 로딩 대기
        
        final_url = page.url
        print(f"   🔗 최종 도착: {final_url[:70]}...")

        mall_name = "기타몰"
        set_price = 0

        # 5. 쇼핑몰별 가격 추출 (상세페이지 + 검색페이지 통합 대응)
        if "auction.co.kr" in final_url or "gmarket.co.kr" in final_url:
            mall_name = "옥션" if "auction" in final_url else "지마켓"
            
            # 케이스 A: 상품 상세 페이지인 경우 (기존 로직)
            selectors = ["#lblSellingPrice", ".price_real", ".price_main", "span.price", ".un-tr-price"]
            
            # 케이스 B: 검색 결과 페이지로 도착한 경우 (새로 추가!)
            # 지마켓 검색 결과 가격: .box__price-value
            # 옥션 검색 결과 가격: .text__price-area_value
            selectors += [".box__price-value", ".text__price-area_value", "strong.price_real_value"]

            for s in selectors:
                el = await page.query_selector(s)
                if el:
                    txt = await el.inner_text()
                    num = re.sub(r'[^0-9]', '', txt)
                    if num:
                        set_price = int(num)
                        print(f"   🎯 가격 발견 ({s}): {set_price}")
                        break
        
        return mall_name, set_price

    except Exception as e:
        print(f"   ⚠️ 에러: {str(e)[:100]}")
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
                    print(f"   ❌ 수집실패 ({mall} - 가격 확인 불가)")
                
                await asyncio.sleep(random.randint(8, 15))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
