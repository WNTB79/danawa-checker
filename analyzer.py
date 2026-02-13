import asyncio
import random
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

async def get_mall_set_price(page, url, idx_name):
    try:
        print(f"🔎 {idx_name} 분석 시작: {url}")
        # 봇 탐지 방지를 위해 좀 더 사람처럼 접속
        await page.goto(url, wait_until="networkidle", timeout=60000)
        
        await asyncio.sleep(5)
        await page.evaluate("window.scrollTo(0, 800)")
        
        # 1. 링크 추출 로직 강화 (자바스크립트로 모든 클릭 가능 요소 수집)
        target_link = await page.evaluate("""
            () => {
                // 가격 비교 테이블의 모든 행을 가져옴
                const rows = document.querySelectorAll('.diff_item, .prc_line, [id^="productItem"]');
                for (const row of rows) {
                    const text = row.innerText;
                    // 유료배송 혹은 배송비 문구가 포함된 행 탐색
                    if (text.includes('배송비') || text.includes('원')) {
                        const a = row.querySelector('a.p_link, a.btn_buy, .prc_c a, .mall_nm a');
                        if (a && a.href && !a.href.includes('javascript')) return a.href;
                    }
                }
                // 실패 시, 그냥 가장 처음에 보이는 몰 링크라도 가져옴
                const firstA = document.querySelector('.prc_c a, .btn_buy a, .mall_nm a');
                return firstA ? firstA.href : null;
            }
        """)

        if not target_link:
            print(f"   ❌ {idx_name}: 링크 추출 실패 (페이지 구조 확인 필요)")
            return "업체미발견", 0

        # 2. 판매처 이동
        print(f"   🚀 판매처 이동: {target_link[:50]}...")
        await page.goto(target_link, wait_until="load", timeout=90000)
        await asyncio.sleep(10)
        
        # 3. 지마켓/옥션 검색 결과 페이지 처리 (클릭해서 상세페이지로!)
        if "gmarket.co.kr/n/search" in page.url or "auction.co.kr/search" in page.url:
            print("   🖱️ 검색 리스트 감지, 첫 번째 상품으로 진입...")
            try:
                # 지마켓/옥션 검색결과에서 상품 클릭 (여러 선택자 대응)
                item_selector = ".box__item-container a, .image__item, .link__item, .item_title a"
                await page.wait_for_selector(item_selector, timeout=10000)
                await page.click(item_selector)
                await asyncio.sleep(10)
            except:
                print("   ⚠️ 검색 결과에서 상품을 클릭하지 못함")

        final_url = page.url
        print(f"   🔗 최종 도착: {final_url[:60]}...")

        mall_name = "기타몰"
        set_price = 0

        # 4. 가격 추출 (최종 상세페이지)
        if "auction.co.kr" in final_url or "gmarket.co.kr" in final_url:
            mall_name = "옥션" if "auction" in final_url else "지마켓"
            # 친구가 본 '설정가'를 찾기 위한 정밀 선택자
            price_selectors = [
                "span.price_inner__price", 
                "del.original-price", 
                "#lblSellingPrice", 
                "strong.price_real_value",
                ".price_real", ".price_main"
            ]

            for s in price_selectors:
                try:
                    el = await page.query_selector(s)
                    if el:
                        txt = await el.inner_text()
                        num = re.sub(r'[^0-9]', '', txt)
                        if num and int(num) > 5000: # 배송비 등 잘못된 가격 방지
                            set_price = int(num)
                            print(f"   🎯 가격 발견 ({s}): {set_price}")
                            break
                except: continue
        
        return mall_name, set_price

    except Exception as e:
        print(f"   ⚠️ 에러: {str(e)[:100]}")
        return "에러", 0

async def main():
    creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
    creds = json.loads(creds_raw)
    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_key(SH_ID)
    
    try:
        wks = sh.worksheet("정산가분석")
    except:
        wks = sh.add_worksheet(title="정산가분석", rows="1000", cols="6")
        wks.append_row(["수집시간", "상품명", "구성", "판매처", "설정가", "정산금(85%)"])

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 실제 브라우저와 거의 흡사한 환경 설정
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            locale="ko-KR"
        )
        page = await context.new_page()

        for prod_name, urls in PRODUCTS.items():
            print(f"\n--- {prod_name} 수집 시작 ---")
            for idx, url in enumerate(urls):
                if not url: continue
                mall, price = await get_mall_set_price(page, url, f"{idx+1}개입")
                
                if price > 0:
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    settle = int(price * 0.85)
                    wks.append_row([now_str, prod_name, f"{idx+1}개입", mall, price, settle])
                    print(f"   ✅ 성공: {mall} / {price}원")
                else:
                    print(f"   ❌ 실패 ({mall})")
                
                await asyncio.sleep(random.randint(10, 15))
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
