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
        # 다나와 로딩 시 스크립트가 다 돌 때까지 대기
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(5)

        # [전략 1] 광고 상품 제외, 지마켓/옥션 중 가장 상단(1위) 링크 찾기
        target_link = await page.evaluate("""() => {
            // 가격 비교 리스트의 상품들 추출
            const rows = Array.from(document.querySelectorAll('.diff_item, .lowest_list tr'));
            for (let row of rows) {
                const mallName = row.innerText;
                const link = row.querySelector('a.item__link, .price_line a');
                if (link && (mallName.includes('G마켓') || mallName.includes('옥션') || mallName.includes('11번가'))) {
                    return link.href;
                }
            }
            // 상단 '최저가 구매하기' 버튼 (백업)
            const topBtn = document.querySelector('.lowest_area a.item__link');
            return topBtn ? topBtn.href : null;
        }""")

        if not target_link:
            print("   ❌ 지마켓/옥션/11번가 판매처를 찾지 못했습니다.")
            return None, 0

        # [전략 2] 새 탭에서 몰 상세페이지 열기 (지마켓 튕김 방지를 위해 Referer 설정)
        new_page = await browser_context.new_page()
        print(f"   🚀 판매처 이동: {target_link[:60]}...")
        await new_page.goto(target_link, wait_until="load", timeout=90000)
        await asyncio.sleep(15) # 보안 우회를 위해 충분히 대기

        # [전략 3] 지마켓 검색 리스트 강제 돌파 (URL에서 상품번호 추출 재진입)
        if "search" in new_page.url or "keyword=" in new_page.url:
            print("   ⚠️ 검색 리스트 감지. 상품번호 추출 후 강제 점프...")
            item_no = re.search(r'(itemno|goodscode|goodsNo)=(\d+)', target_link)
            if item_no:
                num = item_no.group(2)
                direct_url = f"https://item.gmarket.co.kr/Item?goodscode={num}" if "gmarket" in target_link else f"https://itempage3.auction.co.kr/DetailView.aspx?itemno={num}"
                await new_page.goto(direct_url, wait_until="load")
                await asyncio.sleep(10)

        # [전략 4] 지마켓/옥션 보안 우회 스크롤링
        await new_page.mouse.wheel(0, 800)
        await asyncio.sleep(2)
        await new_page.mouse.wheel(0, -400)

        print(f"   🔗 상세페이지 도달: {new_page.url[:60]}")
        mall_name = "지마켓" if "gmarket" in new_page.url else "옥션" if "auction" in new_page.url else "11번가" if "11st" in new_page.url else "기타"
        
        # [전략 5] 가격 데이터 추출 (텍스트 노드 직접 검사)
        price = 0
        price_patterns = [
            "span.price_inner__price", "#lblSellingPrice", "del.original_price", 
            ".price_detail .value", "strong.price_real_value", ".price_real",
            "span.price_main", ".ii_price_fixed"
        ]

        for p in price_patterns:
            try:
                el = await new_page.query_selector(p)
                if el:
                    txt = await el.inner_text()
                    num = int(re.sub(r'[^0-9]', '', txt))
                    if 10000 < num < 1000000:
                        price = num
                        break
            except: continue

        # 패턴 매칭 (최후의 수단)
        if price == 0:
            print("   ⚠️ 일반 추출 실패, 패턴 매칭 시도...")
            body_text = await new_page.inner_text("body")
            # 쉼표 포함된 숫자 + 원 (예: 59,770원)
            matches = re.findall(r'([0-9,]{4,})\s*원', body_text)
            for m in matches:
                num = int(re.sub(r'[^0-9]', '', m))
                if 10000 < num < 1000000:
                    price = num
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
        # 실제 브라우저처럼 보이기 위한 설정
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            java_script_enabled=True
        )

        for prod_name, urls in PRODUCTS.items():
            print(f"\n--- {prod_name} 수집 시작 ---")
            for idx, url in enumerate(urls):
                mall, price = await get_price_final(context, url, f"{idx+1}개입")
                if price > 0:
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    wks.append_row([now, prod_name, f"{idx+1}개입", mall, price, int(price * 0.85)])
                    print(f"   ✅ 시트 기록 성공: {price}원")
                else:
                    print("   ❌ 가격 추출 실패")
                await asyncio.sleep(random.randint(15, 20))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
