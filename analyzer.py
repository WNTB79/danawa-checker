import asyncio
import re
import json
import os
import random
from datetime import datetime
from playwright.async_api import async_playwright
import gspread

# --- AI 설정: 데이터 기록 위치 ---
SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ"
PRODUCTS = {
    "1개입": "콘드1200 60정",
    "2개입": "콘드1200 60정 2개",
    "3개입": "콘드1200 60정 3개",
    "4개입": "콘드1200 60정 4개",
    "5개입": "콘드1200 60정 5개",
    "6개입": "콘드1200 60정 6개"
}

async def collect_data(browser_context, keyword, idx_name):
    page = await browser_context.new_page()
    # 봇 감지를 피하기 위한 모바일 브라우저 위장
    await asyncio.sleep(random.uniform(2, 4))
    
    try:
        print(f"🚀 AI 분석 시작: {idx_name} ({keyword})")
        
        # 지마켓 검색 URL (최저가순 정렬 파라미터 포함)
        search_url = f"https://www.gmarket.co.kr/n/search?keyword={keyword}&s=8"
        
        # 주소창에 직접 입력하는 대신 사람처럼 이동
        await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        
        # 페이지 로딩을 위해 하단으로 살짝 스크롤 (실제 사람처럼 행동)
        await page.mouse.wheel(0, 500)
        await asyncio.sleep(5)
        
        # [핵심] 상세페이지 이동 없이 리스트에서 바로 가격 텍스트 추출
        # 지마켓 검색 리스트의 가격 클래스들을 전수 조사
        price_text = await page.evaluate("""() => {
            const priceEl = document.querySelector('.box__item-container .text__value, .box__price-seller .text__value');
            return priceEl ? priceEl.innerText : null;
        }""")
        
        if price_text:
            price = int(re.sub(r'[^0-9]', '', price_text))
            if 10000 <= price <= 600000:
                print(f"   💰 성공! 가격 발견: {price}원")
                return "지마켓", price

        # 실패 시 옥션으로 즉시 전환 시도
        print(f"   ⚠️ 지마켓 실패, 옥션으로 우회합니다...")
        auction_url = f"https://browse.auction.co.kr/search?keyword={keyword}&s=1"
        await page.goto(auction_url, wait_until="domcontentloaded")
        await asyncio.sleep(5)
        
        price_text_auction = await page.evaluate("""() => {
            const priceEl = document.querySelector('.text__price-seller, .price_seller');
            return priceEl ? priceEl.innerText : null;
        }""")
        
        if price_text_auction:
            price = int(re.sub(r'[^0-9]', '', price_text_auction))
            if 10000 <= price <= 600000:
                print(f"   💰 성공! 옥션 가격 발견: {price}원")
                return "옥션", price

        return None, 0

    except Exception as e:
        print(f"   ❌ 오류 발생: {idx_name} 건너뜁니다.")
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
        # 보안을 뚫기 위해 브라우저 지문(Fingerprint)을 더 정교하게 설정
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1",
            viewport={'width': 375, 'height': 667}, # 모바일 뷰로 접근 (보안이 더 약함)
            is_mobile=True
        )

        for idx_name, keyword in PRODUCTS.items():
            mall, price = await collect_data(context, keyword, idx_name)
            
            if price > 0:
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                wks.append_row([now, "콘드1200", idx_name, mall, price, int(price * 0.85)])
                print(f"   ✅ 시트 기록 완료!")
            
            # 지연 시간을 더 늘려서 봇 감지 회피
            await asyncio.sleep(random.uniform(15, 25))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
