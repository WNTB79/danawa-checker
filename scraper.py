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
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # 1. 페이지 접속
        await page.goto("https://prod.danawa.com/info/?pcode=13412984", wait_until="networkidle")
        
        # 2. 가격 비교 섹션이 로드될 때까지 충분히 대기 및 스크롤
        await asyncio.sleep(6)
        await page.mouse.wheel(0, 1200)
        await asyncio.sleep(2)

        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        rows = []

        # --- [좌측] 무료배송 섹션 추출 ---
        # 이미지의 '무료배송' 아래에 해당하는 영역입니다.
        free_area = soup.select("#lowPrice_l .diff_item")
        if not free_area: # ID가 다를 경우를 대비한 보조 선택자
            free_area = soup.select(".pay_comparison_list.free_delivery .diff_item")

        for i, item in enumerate(free_area[:5], 1):
            price_tag = item.select_one(".prc_c")
            price = price_tag.text.replace(",", "").replace("원", "").strip() if price_tag else "0"
            rows.append([now_str, f"{i}위", "무료배송섹션", price, "무료"])

        # --- [우측] 배송비 유/무료 전체 섹션 추출 ---
        # 이미지의 오른쪽 영역입니다.
        all_area = soup.select("#lowPrice_r .diff_item")
        if not all_area: # 보조 선택자
            all_area = soup.select(".pay_comparison_list:not(.free_delivery) .diff_item")

        for i, item in enumerate(all_area[:5], 1):
            price_tag = item.select_one(".prc_c")
            price = price_tag.text.replace(",", "").replace("원", "").strip() if price_tag else "0"
            # 배송비 텍스트 추출 (예: 배송비 3,000원)
            deliv_tag = item.select_one(".delivery_base")
            delivery = deliv_tag.text.strip() if deliv_tag else "유료"
            rows.append([now_str, f"{i}위", "전체섹션(유/무)", price, delivery])

        print(f"--- 수집 결과: 무료 {len(free_area[:5])}건 / 전체 {len(all_area[:5])}건 ---")

        # --- 구글 시트 저장 ---
        if rows:
            try:
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
            print("❌ 수집된 데이터가 없습니다. (페이지 로딩 문제일 수 있음)")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
