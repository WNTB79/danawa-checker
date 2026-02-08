import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import gspread
import json
import os

SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ" 

async def get_danawa_data():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 실제 사용자가 브라우저를 쓰는 것처럼 속이기 위한 설정 강화
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # 1. 페이지 접속 및 시간차 대기
        print("🔗 다나와 접속 중...")
        await page.goto("https://prod.danawa.com/info/?pcode=13412984", wait_until="load")
        await asyncio.sleep(10) # 페이지가 완전히 그려질 때까지 충분히 대기
        
        # 2. 강제 스크롤 (데이터 로딩 트리거)
        await page.evaluate("window.scrollTo(0, 1000)")
        await asyncio.sleep(3)
        await page.evaluate("window.scrollTo(0, 1500)")
        await asyncio.sleep(2)

        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 모든 가격 아이템을 일단 긁어옵니다
        all_items = soup.select(".diff_item")
        print(f"🔎 발견된 전체 상품 수: {len(all_items)}개")

        rows = []
        free_count = 0
        total_count = 0

        # 데이터 분류 및 정리
        for item in all_items:
            # 가격 추출
            price_tag = item.select_one(".prc_c")
            if not price_tag: continue
            price = price_tag.get_text().replace(",", "").replace("원", "").strip()
            
            # 배송비 정보 추출
            deliv_tag = item.select_one(".delivery_base")
            deliv_text = deliv_tag.get_text().strip() if deliv_tag else "별도"
            
            # 쇼핑몰 정보
            mall_tag = item.select_one(".shop_logo img")
            mall_name = mall_tag['alt'] if mall_tag and 'alt' in mall_tag.attrs else "기타"

            # 분류 로직
            # 1. 무료배송인 경우 (왼쪽 섹션 데이터로 간주)
            if "무료" in deliv_text and free_count < 5:
                free_count += 1
                rows.append([now_str, f"{free_count}위", "무료배송섹션", price, mall_name])
            
            # 2. 전체 (유/무료 포함, 오른쪽 섹션 데이터로 간주)
            if total_count < 5:
                total_count += 1
                rows.append([now_str, f"{total_count}위", "전체섹션(유/무)", price, deliv_text])

        # --- 구글 시트 저장 ---
        if rows:
            try:
                print(f"📊 수집 완료: 무료 {free_count}건 / 전체 {total_count}건. 시트 저장 시도...")
                creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
                creds = json.loads(creds_raw)
                gc = gspread.service_account_from_dict(creds)
                sh = gc.open_by_key(SH_ID)
                wks = sh.get_worksheet(0)
                wks.append_rows(rows)
                print("✅ 시트 저장 성공!")
            except Exception as e:
                print(f"❌ 시트 저장 실패: {e}")
        else:
            print("❌ 수집 실패: 페이지에서 상품 정보를 찾지 못했습니다. (보안 차단 가능성)")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
