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
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)

        async with page.expect_popup() as popup_info:
            print("   🎯 최저가 구매 버튼 클릭!")
            await page.click(".lowest_area a.item__link, .lowest_list .item__link a", timeout=15000)
        
        new_page = await popup_info.value
        await new_page.bring_to_front()
        await asyncio.sleep(8) 

        # [필살기] 지마켓 검색 페이지면 상품번호 추출해서 상세페이지로 강제 리다이렉트
        if "gmarket.co.kr/n/search" in new_page.url:
            print("   🚀 지마켓 검색페이지 감지! 상품번호 추출 후 강제이동...")
            try:
                # URL에서 keyword 값을 상품번호로 간주하거나, 첫번째 상품의 href에서 번호 추출
                item_link = await new_page.get_attribute(".box__item-container a.link__item, .image__item a", "href")
                if item_link:
                    # 번호만 추출 (보통 goodscode= 뒤의 숫자)
                    goodscode = re.search(r'goodscode=(\d+)', item_link)
                    if goodscode:
                        direct_url = f"https://item.gmarket.co.kr/Item?goodscode={goodscode.group(1)}"
                        await new_page.goto(direct_url, wait_until="load")
                        await asyncio.sleep(7)
            except:
                print("   ⚠️ 강제 이동 실패, 수동 클릭 시도")
                await new_page.locator(".box__item-container a").first.click()
                await asyncio.sleep(7)

        print(f"   🔗 최종 페이지: {new_page.url[:60]}")
        
        mall_name = "지마켓" if "gmarket" in new_page.url else "옥션" if "auction" in new_page.url else "11번가" if "11st" in new_page.url else "기타"
        price = 0
        
        # 쇼핑몰별 맞춤형 가격 태그 (설정가 위주)
        selectors = []
        if mall_name == "지마켓":
            selectors = ["span.price_inner__price", "del.original-price", "strong.price_real_value"]
        elif mall_name == "옥션":
            selectors = ["#lblSellingPrice", "span.price_real", "strong.price_real_value"]
        elif mall_name == "11번가":
            selectors = ["del.original_price", ".price_detail .value", ".ii_price_fixed"]
        else:
            selectors = [".price", "span[class*='price']", "strong[class*='price']"]
        
        for s in selectors:
            try:
                el = await new_page.query_selector(s)
                if el:
                    txt = await el.inner_text()
                    num = int(re.sub(r'[^0-9]', '', txt))
                    if num > 10000:
                        price = num
                        print(f"   💰 {mall_name} 가격 발견: {price}원")
                        break
            except: continue
            
        await new_page.close()
        return mall_name, price

    except Exception as e:
        print(f"   ⚠️ 오류: {str(e)[:50]}")
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
            print(f"\n--- {prod_name} 수집 시작 ---")
            for idx, url in enumerate(urls):
                mall, price = await get_price_final(context, url, f"{idx+1}개입")
                if price > 0:
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    wks.append_row([now, prod_name, f"{idx+1}개입", mall, price, int(price * 0.85)])
                    print(f"   ✅ 시트 기록 성공!")
                else:
                    print(f"   ❌ 가격 추출 실패")
                await asyncio.sleep(random.randint(10, 15))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
