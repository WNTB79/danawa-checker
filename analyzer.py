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
        
        # 1. 다나와 페이지 접속
        await page.goto(url, wait_until="networkidle", timeout=60000)
        
        # 2. 가격 비교 리스트 로딩을 위해 충분히 대기 및 스크롤
        await asyncio.sleep(5)
        for _ in range(3): # 여러 번 나눠서 스크롤하여 동적 로딩 유도
            await page.mouse.wheel(0, 500)
            await asyncio.sleep(1)
        
        # 리스트가 로드되었는지 최종 확인
        try:
            await page.wait_for_selector(".diff_item, .prc_line", timeout=15000)
            print("   ✅ 리스트 렌더링 완료")
        except:
            print("   ⚠️ 리스트 요소를 찾는 중...")

        # 3. 자바스크립트를 이용해 유료배송 1위 업체 직접 찾기
        # 이 방식은 BeautifulSoup보다 훨씬 강력하게 현재 화면의 요소를 잡아냅니다.
        target_link = await page.evaluate("""
            () => {
                const items = document.querySelectorAll('.diff_item, [id^="productItem"]');
                for (const item of items) {
                    const text = item.innerText;
                    // '무료배송'이 없으면서 '배송비' 혹은 '원' 문구가 있는 유료배송 업체 찾기
                    if (!text.includes('무료배송') && (text.includes('배송비') || text.includes('원'))) {
                        const aTag = item.querySelector('.prc_c a, .mall_nm a, .btn_buy a, a');
                        if (aTag && aTag.href && !aTag.href.includes('javascript')) {
                            return aTag.href;
                        }
                    }
                }
                // 만약 못 찾았다면 첫 번째 요소라도 반환
                if (items.length > 0) {
                    const firstA = items[0].querySelector('.prc_c a, .btn_buy a, a');
                    return firstA ? firstA.href : null;
                }
                return null;
            }
        """)

        if not target_link:
            print(f"   ❌ {idx_name}: 링크 추출 실패")
            return "업체미발견", 0

        # 4. 쇼핑몰 이동
        print(f"   🚀 판매처 이동: {target_link[:60]}...")
        await page.goto(target_link, wait_until="load", timeout=90000)
        await asyncio.sleep(12) 
        
        final_url = page.url
        print(f"   🔗 최종 도착: {final_url[:70]}...")

        mall_name = "기타몰"
        set_price = 0

        # 5. 가격 추출 (상세페이지 + 검색페이지 통합 대응)
        if "auction.co.kr" in final_url or "gmarket.co.kr" in final_url:
            mall_name = "옥션" if "auction" in final_url else "지마켓"
            
            # 지마켓/옥션의 다양한 가격 태그 (상세페이지 및 검색결과 페이지 포함)
            selectors = [
                "#lblSellingPrice", ".price_real", ".price_main", "span.price", 
                ".box__price-value", ".text__price-area_value", "strong.price_real_value"
            ]

            for s in selectors:
                try:
                    el = await page.query_selector(s)
                    if el:
                        txt = await el.inner_text()
                        num = re.sub(r'[^0-9]', '', txt)
                        if num and int(num) > 0:
                            set_price = int(num)
                            print(f"   🎯 가격 추출 성공 ({s}): {set_price}")
                            break
                except: continue
        
        return mall_name, set_price

    except Exception as e:
        print(f"   ⚠️ 에러 발생: {str(e)[:100]}")
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
        # 봇 탐지 회피를 위한 정교한 컨텍스트 설정
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            locale="ko-KR",
            timezone_id="Asia/Seoul"
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
                    print(f"   ✅ 데이터 기록 완료: {mall} / {price}원")
                else:
                    print(f"   ❌ 최종 데이터 확인 불가 ({mall})")
                
                await asyncio.sleep(random.randint(10, 15))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
