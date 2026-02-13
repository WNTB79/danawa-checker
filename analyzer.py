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
    page = await browser_context.new_page()
    try:
        print(f"🔎 {idx_name} 분석: {url}")
        # 페이지가 완전히 로드될 때까지 넉넉히 대기
        await page.goto(url, wait_until="networkidle", timeout=60000)
        
        # 버튼이 화면에 보여야 클릭 가능하므로 스크롤 내림
        await page.mouse.wheel(0, 500)
        await asyncio.sleep(3)

        print("   🎯 최저가 구매 버튼 찾는 중...")
        
        # [전략] 텍스트가 '최저가 구매하기'인 요소를 찾아서 클릭 (새 탭 대기)
        async with page.expect_popup() as popup_info:
            # 1. '최저가 구매하기' 텍스트를 가진 링크 우선 타격
            # 2. 실패 시 클래스 기반 타격
            try:
                btn = page.get_by_text("최저가 구매하기").first
                await btn.click(timeout=15000)
            except:
                await page.click(".lowest_area a.item__link, .lowest_list .item__link a", timeout=15000)
        
        new_page = await popup_info.value
        await new_page.bring_to_front()
        print("   🚀 쇼핑몰 새 탭 진입 완료!")
        
        # 지마켓/옥션은 로딩이 매우 무거우므로 넉넉히 대기
        await asyncio.sleep(12) 

        # 지마켓/옥션 검색 리스트 대응
        if "search" in new_page.url or "keyword=" in new_page.url:
            print("   ⚠️ 검색 리스트 발견! 첫 상품 클릭...")
            try:
                # 첫 번째 상품 이미지나 제목을 클릭
                await new_page.locator(".box__item-container a, .image__item, .link__item").first.click(timeout=10000)
                await asyncio.sleep(8)
            except: pass

        print(f"   🔗 최종 도착지: {new_page.url[:60]}")
        
        mall_name = "지마켓" if "gmarket" in new_page.url else "옥션" if "auction" in new_page.url else "기타"
        price = 0
        
        # 설정가 추출용 정밀 선택자
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
        print(f"   ⚠️ 오류: {str(e)[:100]}")
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
                    print("   ✅ 시트 기록 성공")
                
                # 다음 상품 분석 전 충분한 휴식 (차단 방지)
                await asyncio.sleep(random.randint(8, 12))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
