import asyncio
import re
import json
import os
import random
from datetime import datetime
from playwright.async_api import async_playwright
import gspread

SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ"
# URL을 상세페이지가 아닌 '검색 결과' URL로 변경 (더 안정적임)
PRODUCTS = {
    "콘드1200": [
        "https://search.danawa.com/dsearch.php?query=13412984", 
        "https://search.danawa.com/dsearch.php?query=13413059",
        "https://search.danawa.com/dsearch.php?query=13413086", 
        "https://search.danawa.com/dsearch.php?query=13413254",
        "https://search.danawa.com/dsearch.php?query=13678937", 
        "https://search.danawa.com/dsearch.php?query=13413314"
    ]
}

async def get_price_final(browser_context, url, idx_name):
    page = await browser_context.new_page()
    try:
        print(f"🔎 {idx_name} 분석: {url}")
        # 다나와 검색 리스트 페이지 접속
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)

        # [전략] 상세페이지로 들어가지 않고, 검색 결과에 노출된 '지마켓/옥션' 링크를 바로 추출
        target_link = await page.evaluate("""() => {
            // 가격비교 영역 내의 몰 링크들 탐색
            const links = Array.from(document.querySelectorAll('a[href*="bridge/loadingBridge"]'));
            for (let l of links) {
                const text = l.innerText || "";
                const mall = l.parentElement.innerText || "";
                if (mall.includes('G마켓') || mall.includes('옥션') || mall.includes('11번가') || text.includes('최저가')) {
                    return l.href;
                }
            }
            return null;
        }""")

        if not target_link:
            # 실패 시 기존 상세페이지 버튼이라도 시도
            target_link = await page.evaluate("() => document.querySelector('.btn_buy, .lowest_area a')?.href")

        if not target_link:
            print("   ❌ 판매처 링크 추출 실패")
            return None, 0

        # 쇼핑몰 이동
        new_page = await browser_context.new_page()
        print(f"   🚀 쇼핑몰 점프...")
        await new_page.goto(target_link, wait_until="load", timeout=90000)
        await asyncio.sleep(12)

        # 지마켓/옥션 리스트 튕김 대응
        if "search" in new_page.url:
            item_no = re.search(r'(itemno|goodscode|goodsNo)=(\d+)', target_link)
            if item_no:
                num = item_no.group(2)
                direct = f"https://item.gmarket.co.kr/Item?goodscode={num}" if "gmarket" in target_link else f"https://itempage3.auction.co.kr/DetailView.aspx?itemno={num}"
                await new_page.goto(direct, wait_until="load")
                await asyncio.sleep(8)

        print(f"   🔗 최종 도착: {new_page.url[:50]}...")
        mall_name = "지마켓" if "gmarket" in new_page.url else "옥션" if "auction" in new_page.url else "11번가" if "11st" in new_page.url else "기타"
        
        # 가격 추출
        price = 0
        content = await new_page.content()
        # 1. 태그 기반
        for s in ["span.price_inner__price", "#lblSellingPrice", "del.original_price", ".price_real"]:
            el = await new_page.query_selector(s)
            if el:
                txt = await el.inner_text()
                num = int(re.sub(r'[^0-9]', '', txt))
                if 10000 < num < 1000000: price = num; break
        
        # 2. 패턴 기반 (11번가 등에서 성공했던 로직)
        if price == 0:
            matches = re.findall(r'([0-9,]{4,})\s*원', content)
            for m in matches:
                num = int(re.sub(r'[^0-9]', '', m))
                if 10000 < num < 1000000: price = num; break

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
        # 스텔스 모드와 유사한 설정
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )

        for prod_name, urls in PRODUCTS.items():
            print(f"\n--- {prod_name} 수집 시작 ---")
            for idx, url in enumerate(urls):
                mall, price = await get_price_final(context, url, f"{idx+1}개입")
                if price > 0:
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    wks.append_row([now, prod_name, f"{idx+1}개입", mall, price, int(price * 0.85)])
                    print(f"   ✅ 시트 기록 완료: {price}원")
                else:
                    print("   ❌ 수집 실패")
                await asyncio.sleep(random.randint(15, 20))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
