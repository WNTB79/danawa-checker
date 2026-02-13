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
        await asyncio.sleep(5)
        
        # 버튼을 찾기 위해 화면을 조금 내림
        await page.evaluate("window.scrollTo(0, 500)")
        await asyncio.sleep(2)

        new_page = None
        print("   🎯 구매 버튼 탐색 및 클릭 시도...")

        # [전략 1] '구매하기' 혹은 '최저가' 글자가 포함된 버튼/링크 직접 클릭
        try:
            async with page.expect_popup(timeout=20000) as popup_info:
                # '구매하기'라는 글자가 들어간 모든 요소를 뒤져서 클릭
                await page.locator("a:has-text('구매하기'), a:has-text('최저가')").first.click(timeout=15000)
            new_page = await popup_info.value
        except Exception as e:
            print(f"   ⚠️ 일반 클릭 실패, 강제 링크 추출 시도...")
            # [전략 2] 클릭 실패 시 페이지 내의 지마켓/옥션/11번가 이동 링크를 직접 찾아내서 강제 이동
            target_href = await page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a[href*="bridge/loadingBridge"]'));
                return links.length > 0 ? links[0].href : null;
            }""")
            
            if target_href:
                new_page = await browser_context.new_page()
                await new_page.goto(target_href, wait_until="load")
            else:
                print("   ❌ 이동 가능한 링크를 찾지 못했습니다.")
                return None, 0

        # 쇼핑몰 페이지 진입 성공 후
        await new_page.bring_to_front()
        await asyncio.sleep(10)

        # 지마켓 검색 페이지 리다이렉트 처리
        if "gmarket.co.kr/n/search" in new_page.url:
            print("   🚀 지마켓 검색페이지 탈출 시도...")
            try:
                first_item_link = await new_page.get_attribute(".box__item-container a, .image__item a", "href")
                if first_item_link:
                    goodscode = re.search(r'goodscode=(\d+)', first_item_link)
                    if goodscode:
                        await new_page.goto(f"https://item.gmarket.co.kr/Item?goodscode={goodscode.group(1)}")
                        await asyncio.sleep(8)
            except: pass

        print(f"   🔗 최종 도착: {new_page.url[:60]}")
        
        mall_name = "지마켓" if "gmarket" in new_page.url else "옥션" if "auction" in new_page.url else "11번가" if "11st" in new_page.url else "기타"
        price = 0
        
        # 몰별 가격 태그 보강
        selectors = [
            "span.price_inner__price", "#lblSellingPrice", "del.original_price", 
            ".price_detail .value", "strong.price_real_value", ".price_real"
        ]
        
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
                    print("   ✅ 시트 업데이트 완료!")
                else:
                    print("   ❌ 최종 가격 수집 실패")
                await asyncio.sleep(random.randint(10, 15))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
