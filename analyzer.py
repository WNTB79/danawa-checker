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
        # 다나와 접속 시 유저 에이전트 무작위성 부여
        await page.goto(url, wait_until="load", timeout=60000)
        await asyncio.sleep(7)
        
        # [핵심] 다나와가 요소를 숨겨도 '전체 HTML 소스'에서 지마켓/옥션 브릿지 주소 강제 추출
        content = await page.content()
        # 다나와 브릿지(loadingBridge) 패턴 찾기
        links = re.findall(r'https://prod\.danawa\.com/bridge/loadingBridge\.html\?[^\s\'"]+', content)
        
        target_link = None
        if links:
            # 첫 번째 링크를 타겟으로 잡음
            target_link = links[0].replace('&amp;', '&')
            print(f"   🎯 브릿지 링크 강제 포착!")
        else:
            # 정석적인 방법으로 재시도
            target_link = await page.evaluate("() => { const a = document.querySelector('.diff_item a, .btn_buy'); return a ? a.href : null; }")

        if not target_link:
            print(f"   ❌ {idx_name}: 링크 추출 실패")
            return "업체미발견", 0

        # 1차 이동 (다나와 브릿지 페이지)
        print(f"   🚀 판매처 이동...")
        await page.goto(target_link, wait_until="load", timeout=60000)
        await asyncio.sleep(10)

        # 만약 지마켓 검색페이지라면 첫 상품 클릭 (3단계 돌파)
        if "gmarket.co.kr/n/search" in page.url:
            print("   🖱️ 지마켓 리스트 클릭 중...")
            try:
                await page.click(".box__item-container a, .image__item", timeout=10000)
                await asyncio.sleep(8)
            except: pass

        final_url = page.url
        print(f"   🔗 최종 도착: {final_url[:60]}...")

        mall_name = "기타몰"
        set_price = 0

        # 가격 추출 (스샷에서 본 설정가 타겟팅)
        if "auction.co.kr" in final_url or "gmarket.co.kr" in final_url:
            mall_name = "옥션" if "auction" in final_url else "지마켓"
            # 59,770원 같은 설정가용 선택자 대폭 보강
            for s in ["span.price_inner__price", "del.original-price", "#lblSellingPrice", "strong.price_real_value"]:
                el = await page.query_selector(s)
                if el:
                    txt = await el.inner_text()
                    num = re.sub(r'[^0-9]', '', txt)
                    if num and int(num) > 1000:
                        set_price = int(num)
                        print(f"   💰 가격 발견: {set_price}")
                        break
        
        return mall_name, set_price

    except Exception as e:
        print(f"   ⚠️ 에러 발생: {str(e)[:50]}")
        return "에러", 0

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
        page = await context.new_page()

        for prod_name, urls in PRODUCTS.items():
            print(f"\n--- {prod_name} 수집 시작 ---")
            for idx, url in enumerate(urls):
                mall, price = await get_mall_set_price(page, url, f"{idx+1}개입")
                if price > 0:
                    wks.append_row([datetime.now().strftime('%Y-%m-%d %H:%M:%S'), prod_name, f"{idx+1}개입", mall, price, int(price*0.85)])
                    print(f"   ✅ 수집 완료: {price}원")
                await asyncio.sleep(random.randint(10, 15))
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
