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
        
        # [전략 1] 다나와 버튼 클릭 대신 '링크 주소'만 먼저 따오기
        target_href = await page.evaluate("""() => {
            const link = document.querySelector('.lowest_area a, .prc_c a');
            return link ? link.href : null;
        }""")

        if not target_href: return None, 0

        # [전략 2] 지마켓/옥션이면 주소에서 상품번호 추출해서 직접 상세페이지로 꽂기
        # 다나와 브릿지 주소엔 보통 상품번호가 포함되어 있음
        item_no_match = re.search(r'(itemno|goodscode|goodsNo)=(\d+)', target_href)
        
        new_page = await browser_context.new_page()
        if item_no_match:
            item_no = item_no_match.group(2)
            if "gmarket" in target_href.lower():
                direct_url = f"https://item.gmarket.co.kr/Item?goodscode={item_no}"
            elif "auction" in target_href.lower():
                direct_url = f"https://itempage3.auction.co.kr/DetailView.aspx?itemno={item_no}"
            else:
                direct_url = target_href
            
            print(f"   🚀 직접 주소로 점프: {direct_url[:50]}...")
            await new_page.goto(direct_url, wait_until="load", timeout=60000)
        else:
            # 번호 추출 실패 시 일반적인 팝업 대기 클릭
            async with page.expect_popup(timeout=20000) as popup_info:
                await page.locator(".lowest_area a, .prc_c a").first.click()
            new_page = await popup_info.value

        await new_page.bring_to_front()
        await asyncio.sleep(10)

        # 지마켓 검색창으로 또 튕겼을 때의 마지막 보험
        if "search" in new_page.url:
            print("   ⚠️ 검색창 튕김! 첫 상품 강제 이동...")
            # 텍스트에서 숫자를 찾아 주소 재조합
            raw_content = await new_page.content()
            code_match = re.search(r'goodscode=(\d+)', raw_content)
            if code_match:
                await new_page.goto(f"https://item.gmarket.co.kr/Item?goodscode={code_match.group(1)}")
                await asyncio.sleep(7)

        print(f"   🔗 최종 도착: {new_page.url[:60]}")
        mall_name = "지마켓" if "gmarket" in new_page.url else "옥션" if "auction" in new_page.url else "11번가" if "11st" in new_page.url else "기타"
        
        price = 0
        # 가격 추출 (더 넓은 범위의 텍스트 스캔)
        selectors = [
            "span.price_inner__price", "#lblSellingPrice", "del.original_price", 
            ".price_detail .value", "strong.price_real_value", ".price_real",
            ".price_inner", "div[class*='price']"
        ]
        
        # 1차 선택자 시도
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
        
        # 2차: 화면 전체 텍스트 패턴 매칭 (옥션/지마켓 설정가 완벽 대응)
        if price == 0:
            print("   ⚠️ 패턴 매칭 가동...")
            content = await new_page.content()
            # "설정가", "판매가", "시중가" 등의 키워드 근처 숫자 찾기
            matches = re.findall(r'([0-9,]{4,})\s*원', content)
            for m in matches:
                num = int(re.sub(r'[^0-9]', '', str(m)))
                if 10000 < num < 1000000:
                    price = num
                    print(f"   🎯 패턴 매칭으로 찾음: {price}")
                    break

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
