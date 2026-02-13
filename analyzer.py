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
        await asyncio.sleep(4)
        
        new_page = None
        try:
            async with page.expect_popup(timeout=20000) as popup_info:
                # 더 넓은 범위의 클릭 셀렉터
                await page.locator("a:has-text('구매하기'), a.btn_buy, .lowest_area a, .prc_c a").first.click()
            new_page = await popup_info.value
        except:
            link = await page.evaluate("() => document.querySelector('.lowest_area a, .prc_c a')?.href")
            if link:
                new_page = await browser_context.new_page()
                await new_page.goto(link, wait_until="load")

        if not new_page: return None, 0
        
        await new_page.bring_to_front()
        await asyncio.sleep(12)

        # [수정] 지마켓 검색 리스트 탈출 로직 (문법 에러 해결)
        if "search" in new_page.url or "keyword=" in new_page.url:
            print("   🚀 지마켓/옥션 리스트 탈출 시도...")
            try:
                # locator().first 뒤에 바로 get_attribute를 쓰지 않고 객체를 먼저 받음
                first_item_locator = new_page.locator(".box__item-container a, .link__item, .image__item a").first
                href = await first_item_locator.get_attribute("href")
                if href:
                    target_url = href if href.startswith('http') else f"https:{href}"
                    await new_page.goto(target_url, wait_until="load")
                    await asyncio.sleep(8)
            except Exception as e:
                print(f"   ⚠️ 리스트 탈출 중 오류: {e}")

        print(f"   🔗 상세페이지 도착: {new_page.url[:60]}")
        mall_name = "지마켓" if "gmarket" in new_page.url else "옥션" if "auction" in new_page.url else "11번가" if "11st" in new_page.url else "기타"
        
        price = 0
        # 1. 셀렉터 기반 추출 (옥션/지마켓 원가 타겟)
        selectors = [
            "span.price_inner__price", "#lblSellingPrice", "del.original_price", 
            ".price_detail .value", "strong.price_real_value", ".price_real",
            "span.price_main", "div.price_area"
        ]
        
        for s in selectors:
            try:
                el = await new_page.query_selector(s)
                if el:
                    txt = await el.inner_text()
                    num = int(re.sub(r'[^0-9]', '', txt))
                    if 10000 < num < 1000000:
                        price = num
                        break
            except: continue
        
        # 2. 패턴 매칭 강화 (옥션/지마켓 특수 문자 대응)
        if price == 0:
            print("   ⚠️ 패턴 매칭 가동...")
            content = await new_page.content()
            # 쉼표 포함/미포함 숫자 + 원 패턴
            matches = re.findall(r'([0-9,]{4,})\s*원', content)
            # 숫자로만 된 패턴 (지마켓/옥션 가격 텍스트)
            matches += re.findall(r'price["\']\s*:\s*(\d{5,})', content)
            
            for m in matches:
                num = int(re.sub(r'[^0-9]', '', str(m)))
                if 10000 < num < 1000000:
                    price = num
                    break

        if price > 0:
            print(f"   💰 {mall_name} 최종 가격: {price}원")
            
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
            print(f"\n--- {prod_name} 수집 시작 ---")
            for idx, url in enumerate(urls):
                mall, price = await get_price_final(context, url, f"{idx+1}개입")
                if price > 0:
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    wks.append_row([now, prod_name, f"{idx+1}개입", mall, price, int(price * 0.85)])
                    print("   ✅ 시트 기록 성공!")
                else:
                    print("   ❌ 가격 추출 실패")
                await asyncio.sleep(random.randint(10, 15))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
