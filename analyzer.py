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
        # 페이지 로딩 및 판매처 목록이 나타날 때까지 스크롤하며 대기
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.evaluate("window.scrollTo(0, 800)")
        
        # [핵심] 판매처 리스트(지마켓, 옥션 등)가 로딩될 때까지 최대 15초 대기
        try:
            await page.wait_for_selector(".lowest_list, .diff_item", timeout=15000)
        except:
            print("   ⚠️ 판매처 목록 로딩 지연 중...")

        await asyncio.sleep(5)

        # [전략 1] 광고 제외, 지마켓/옥션/11번가 중 진짜 1위(최상단) 찾기
        target_link = await page.evaluate("""() => {
            const mallKeywords = ['G마켓', '옥션', '11번가'];
            // 모든 가격 비교 행을 가져옴
            const items = document.querySelectorAll('.lowest_list tr, .diff_item');
            
            for (const item of items) {
                const text = item.innerText;
                const link = item.querySelector('a[href*="bridge/loadingBridge"]');
                
                // 몰 이름이 키워드에 포함되어 있고 링크가 있다면 첫 번째 것을 반환
                if (link && mallKeywords.some(k => text.includes(k))) {
                    return link.href;
                }
            }
            return null;
        }""")

        # 링크를 못 찾았다면 최후의 수단으로 '최저가 구매하기' 버튼이라도 긁음
        if not target_link:
            target_link = await page.evaluate("() => document.querySelector('.lowest_area a.item__link')?.href")

        if not target_link:
            print("   ❌ 판매처 탐색 실패 (지마켓/옥션/11번가 없음)")
            return None, 0

        # [전략 2] 상세페이지 이동 및 보안 우회
        new_page = await browser_context.new_page()
        print(f"   🚀 판매처 이동 중...")
        await new_page.goto(target_link, wait_until="load", timeout=90000)
        await asyncio.sleep(12)

        # 지마켓 검색창 튕김 방지 (주소 재조합)
        if "search" in new_page.url or "keyword=" in new_page.url:
            item_no = re.search(r'(itemno|goodscode|goodsNo)=(\d+)', target_link)
            if item_no:
                num = item_no.group(2)
                direct = f"https://item.gmarket.co.kr/Item?goodscode={num}" if "gmarket" in target_link else f"https://itempage3.auction.co.kr/DetailView.aspx?itemno={num}"
                await new_page.goto(direct, wait_until="load")
                await asyncio.sleep(8)

        # 상세페이지 로딩 후 스크롤 (봇 방지 우회)
        await new_page.evaluate("window.scrollTo(0, 500)")
        await asyncio.sleep(3)

        print(f"   🔗 최종 페이지: {new_page.url[:60]}")
        mall_name = "지마켓" if "gmarket" in new_page.url else "옥션" if "auction" in new_page.url else "11번가" if "11st" in new_page.url else "기타"
        
        # [전략 3] 가격 추출 (텍스트 기반 패턴 매칭 강화)
        price = 0
        selectors = ["span.price_inner__price", "#lblSellingPrice", "del.original_price", ".price_real", "strong.price_real_value"]
        
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

        if price == 0:
            # 패턴 매칭 백업
            body_text = await new_page.inner_text("body")
            matches = re.findall(r'([0-9,]{4,})\s*원', body_text)
            for m in matches:
                num = int(re.sub(r'[^0-9]', '', m))
                if 10000 < num < 1000000:
                    price = num; break

        await new_page.close()
        return mall_name, price

    except Exception as e:
        print(f"   ⚠️ 오류 발생: {str(e)[:50]}")
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
                    print(f"   ✅ 기록 성공: {price}원")
                else:
                    print("   ❌ 수집 실패")
                await asyncio.sleep(random.randint(15, 20))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
