import asyncio
import re
import json
import os
import random
from datetime import datetime
from playwright.async_api import async_playwright
import gspread

# --- AI 설정: 가장 확실한 데이터 소스 정의 ---
SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ"
# 상품명만 알면 AI가 주소를 찾아갑니다.
PRODUCTS = {
    "1개입": "콘드1200 60정",
    "2개입": "콘드1200 60정 2개",
    "3개입": "콘드1200 60정 3개",
    "4개입": "콘드1200 60정 4개",
    "5개입": "콘드1200 60정 5개",
    "6개입": "콘드1200 60정 6개"
}

async def solve_price(page):
    """AI가 페이지 내에서 가격처럼 보이는 가장 큰 숫자를 찾아냅니다."""
    try:
        # 화면에 보이는 모든 텍스트 추출
        body_text = await page.inner_text("body")
        # '원' 앞의 숫자 패턴 추출 (예: 59,700원)
        price_candidates = re.findall(r'([0-9,]{4,})\s*원', body_text)
        
        valid_prices = []
        for p in price_candidates:
            num = int(re.sub(r'[^0-9]', '', p))
            # 콘드1200 가격대(1만 원 ~ 50만 원)에 맞는 숫자만 필터링
            if 10000 <= num <= 500000:
                valid_prices.append(num)
        
        # 최저가를 찾되, 너무 낮은 가격(배송비 등)은 제외하기 위해 정렬 후 첫 번째 선택
        return min(valid_prices) if valid_prices else 0
    except:
        return 0

async def collect_data(browser_context, keyword, idx_name):
    page = await browser_context.new_page()
    # 사람처럼 보이기 위한 랜덤 딜레이
    await asyncio.sleep(random.uniform(1, 3))
    
    try:
        print(f"🚀 AI 분석 시작: {idx_name} ({keyword})")
        
        # [핵심] 쇼핑몰 검색 페이지로 직접 진입 (다나와를 거치지 않음)
        # 지마켓이 가장 데이터가 명확하므로 지마켓을 우선 타격합니다.
        search_url = f"https://www.gmarket.co.kr/n/search?keyword={keyword}&s=8" # s=8: 최저가순 정렬
        
        await page.goto(search_url, wait_until="domcontentloaded")
        await asyncio.sleep(5)
        
        # 첫 번째 상품의 상세 페이지 주소 가져오기
        first_item = page.locator(".box__item-container a").first
        item_link = await first_item.get_attribute("href")
        
        if item_link:
            await page.goto(item_link, wait_until="networkidle")
            await asyncio.sleep(5)
            
            price = await solve_price(page)
            mall = "지마켓"
            
            if price > 0:
                print(f"   💰 성공! {mall} 가격 발견: {price}원")
                return mall, price
        
        print(f"   ❌ {idx_name} 수집 실패")
        return None, 0

    except Exception as e:
        print(f"   ⚠️ 분석 중 에러 발생 (무시하고 다음 진행)")
        return None, 0
    finally:
        await page.close()

async def main():
    # 1. 구글 시트 연결
    creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
    creds = json.loads(creds_raw)
    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_key(SH_ID)
    wks = sh.worksheet("정산가분석")

    async with async_playwright() as p:
        # 2. 브라우저 실행 (사람처럼 보이는 위장 설정)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )

        for idx_name, keyword in PRODUCTS.items():
            mall, price = await collect_data(context, keyword, idx_name)
            
            if price > 0:
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                # 데이터 기록: [일시, 제품명, 구분, 판매처, 원가, 정산가]
                wks.append_row([now, "콘드1200", idx_name, mall, price, int(price * 0.85)])
                print(f"   ✅ 시트 기록 완료!")
            
            # 다음 수집 전 휴식 (봇 감지 회피)
            await asyncio.sleep(random.uniform(10, 20))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
