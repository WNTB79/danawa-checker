import asyncio
import re
import json
import os
import random  # 추가됨
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

        # 1. 다나와 '최저가 구매하기' 버튼 링크 추출
        target_link = await page.evaluate("""() => {
            const buttons = Array.from(document.querySelectorAll('a, button'));
            const buyBtn = buttons.find(b => b.innerText.includes('최저가 구매하기'));
            return buyBtn ? buyBtn.href : null;
        }""")

        if not target_link:
            print("   ❌ 최저가 버튼을 찾을 수 없습니다.")
            return None, 0

        # 2. 판매처 이동
        print("   🚀 판매처 이동 중...")
        await page.goto(target_link, wait_until="load", timeout=90000)
        await asyncio.sleep(8)

        # 3. [지마켓 튕김 방지] 만약 엉뚱한 검색페이지라면 상품번호로 강제 이동
        current_url = page.url
        if "gmarket.co.kr" in current_url and ("keyword=" in current_url or "search" in current_url):
            print("   ⚠️ 지마켓 검색페이지 튕김 감지! 상품번호 추출 시도...")
            # URL에서 itemno 혹은 goodscode 추출
            item_no_match = re.search(r'(itemno|goodscode)=([0-9]+)', target_link)
            if item_no_match:
                item_no = item_no_match.group(2)
                direct_url = f"https://item.gmarket.co.kr/Item?goodscode={item_no}"
                print(f"   🎯 상세페이지 직접 강제 진입: {direct_url}")
                await page.goto(direct_url, wait_until="load", timeout=60000)
                await asyncio.sleep(7)

        final_url = page.url
        mall_name = "지마켓" if "gmarket" in final_url else "옥션" if "auction" in final_url else "기타"
        print(f"   🔗 최종 도착: {mall_name}")

        # 4. 설정가(59,770원) 추출
        price = 0
        price_selectors = [
            "span.price_inner__price", "del.original-price", 
            "#lblSellingPrice", "strong.price_real_value", ".price_real"
        ]

        for s in price_selectors:
            try:
                el = await page.query_selector(s)
                if el:
                    txt = await el.inner_text()
                    num = int(re.sub(r'[^0-9]', '', txt))
                    if num > 10000:
                        price = num
                        print(f"   💰 설정가 발견: {price}원")
                        break
            except: continue
            
        return mall_name, price

    except Exception as e:
        print(f"   ⚠️ 오류 발생: {str(e)[:100]}")
        return None, 0

async def main():
    try:
        creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
        creds = json.loads(creds_raw)
        gc = gspread.service_account_from_dict(creds)
        sh = gc.open_by_key(SH_ID)
        wks = sh.worksheet("정산가분석")
    except Exception as e:
        print(f"❌ 구글 시트 연결 실패: {e}")
        return

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
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    wks.append_row([now, prod_name, f"{idx+1}개입", mall, price, int(price * 0.85)])
                    print("   ✅ 시트 기록 완료!")
                
                # 대기 시간 추가 (에러 해결됨)
                await asyncio.sleep(random.randint(10, 15))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
