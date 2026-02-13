import asyncio
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

async def get_price_final(page, url, idx_name):
    try:
        print(f"🔎 {idx_name} 분석: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        # [전략 1] 스샷에 나온 '최저가 구매하기' 버튼의 텍스트를 직접 찾아서 클릭/링크 추출
        target_link = await page.evaluate("""() => {
            const buttons = Array.from(document.querySelectorAll('a, button'));
            const buyBtn = buttons.find(b => b.innerText.includes('최저가 구매하기'));
            return buyBtn ? buyBtn.href : null;
        }""")

        # 버튼이 안 잡힐 경우를 대비한 2차 수집 (스샷의 파란색 최저가 숫자 옆 버튼)
        if not target_link:
            target_link = await page.evaluate("() => { const a = document.querySelector('.lowest_area a.item__link'); return a ? a.href : null; }")

        if not target_link:
            print(f"   ❌ 최저가 버튼 링크 추출 실패")
            return None, 0

        # 판매처로 이동
        print(f"   🚀 판매처(1위) 이동 중...")
        await page.goto(target_link, wait_until="load", timeout=90000)
        await asyncio.sleep(10)

        # [전략 2] 지마켓/옥션 검색 리스트 처리
        if "gmarket.co.kr/n/search" in page.url or "auction.co.kr/search" in page.url:
            print("   🖱️ 검색 리스트 발견! 첫 번째 상품으로 재진입...")
            try:
                # 스샷의 상품 이미지나 링크 클릭
                await page.click(".box__item-container a, .image__item, .link__item", timeout=7000)
                await asyncio.sleep(10)
            except: pass

        final_url = page.url
        mall_name = "지마켓" if "gmarket" in final_url else "옥션" if "auction" in final_url else "기타"
        print(f"   🔗 최종 도착: {mall_name} ({final_url[:50]}...)")

        # [전략 3] 설정가(할인 전 가격) 정밀 추출
        price = 0
        # 스샷의 '59,770원' 위치를 타겟팅하는 선택자들
        price_selectors = [
            "span.price_inner__price", # 지마켓 설정가 (진짜 판매자가 적은 가격)
            "del.original-price",      # 지마켓 취소선 가격
            "#lblSellingPrice",        # 옥션 설정가
            ".price_real", ".price_main"
        ]

        for s in price_selectors:
            try:
                el = await page.query_selector(s)
                if el:
                    txt = await el.inner_text()
                    num = int(re.sub(r'[^0-9]', '', txt))
                    if num > 10000: # 1만원 이상인 경우만 (정상 설정가)
                        price = num
                        print(f"   🎯 {mall_name} 설정가 추출 완료: {price}원")
                        break
            except: continue
            
        return mall_name, price

    except Exception as e:
        print(f"   ⚠️ 오류: {str(e)[:50]}")
        return None, 0

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
            print(f"\n--- {prod_name} 분석 시작 ---")
            for idx, url in enumerate(urls):
                mall, price = await get_price_final(page, url, f"{idx+1}개입")
                if price > 0:
                    wks.append_row([
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        prod_name, f"{idx+1}개입", mall, price, int(price * 0.85)
                    ])
                    print(f"   ✅ 시트 업데이트 완료!")
                else:
                    print(f"   ❌ 데이터 수집 실패 (지마켓/옥션 아님 혹은 페이지 오류)")
                await asyncio.sleep(random.randint(12, 15))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
