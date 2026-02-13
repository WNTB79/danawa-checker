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
        
        # 다나와에서 구매 버튼 클릭 및 팝업 대기
        new_page = None
        try:
            async with page.expect_popup(timeout=20000) as popup_info:
                # 텍스트 '구매하기'가 들어간 링크 클릭
                await page.locator("a:has-text('구매하기'), a.btn_buy, .lowest_area a").first.click()
            new_page = await popup_info.value
        except:
            # 클릭 실패 시 직접 링크 추출 시도
            link = await page.evaluate("() => document.querySelector('.lowest_area a, .prc_c a')?.href")
            if link:
                new_page = await browser_context.new_page()
                await new_page.goto(link, wait_until="load")

        if not new_page: return None, 0
        
        await new_page.bring_to_front()
        await asyncio.sleep(12) # 로딩 충분히 대기

        # 지마켓 검색 페이지인 경우 첫 상품으로 강제 이동 로직 강화
        if "search" in new_page.url:
            print("   🚀 지마켓 검색 리스트에서 탈출 시도...")
            first_item = await new_page.locator(".box__item-container a, .link__item, .image__item a").first
            href = await first_item.get_attribute("href")
            if href:
                await new_page.goto(href if href.startswith('http') else f"https:{href}")
                await asyncio.sleep(8)

        print(f"   🔗 상세페이지 도착: {new_page.url[:60]}")
        
        mall_name = "지마켓" if "gmarket" in new_page.url else "옥션" if "auction" in new_page.url else "11번가" if "11st" in new_page.url else "기타"
        
        # [핵심] 가격 추출 전략: 화면에 보이는 모든 텍스트를 검사
        price = 0
        
        # 1. 널리 알려진 가격 선택자들 먼저 시도
        selectors = [
            "span.price_inner__price", "#lblSellingPrice", "del.original_price", 
            ".price_detail .value", "strong.price_real_value", ".price_real",
            ".price_main", ".price-info .price"
        ]
        
        for s in selectors:
            try:
                el = await new_page.query_selector(s)
                if el:
                    txt = await el.inner_text()
                    num = int(re.sub(r'[^0-9]', '', txt))
                    if 10000 < num < 1000000: # 현실적인 가격 범위
                        price = num
                        break
            except: continue
        
        # 2. 실패 시: '원' 앞에 있는 숫자나 특정 큰 금액 텍스트 패턴 매칭 (가장 확실한 백업)
        if price == 0:
            print("   ⚠️ 일반 추출 실패, 패턴 매칭 시도...")
            content = await new_page.content()
            # 59,770원 같은 패턴 찾기
            matches = re.findall(r'([0-9,]{4,})\s*원', content)
            for m in matches:
                num = int(re.sub(r'[^0-9]', '', m))
                if 10000 < num < 1000000:
                    price = num
                    break

        if price > 0:
            print(f"   💰 {mall_name} 최종 가격: {price}원")
            
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
                    print("   ✅ 시트 기록 성공!")
                else:
                    print("   ❌ 가격 추출 실패")
                await asyncio.sleep(random.randint(10, 15))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
