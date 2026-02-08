import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import gspread
import json
import os

# === 시트 ID (확인하신 ID 그대로 유지) ===
SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ" 

async def get_danawa_data():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 다나와 상품 페이지 접속
        await page.goto("https://prod.danawa.com/info/?pcode=13412984")
        await asyncio.sleep(7) # 로딩 대기
        
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        rows = []

        # 1. 무료배송 섹션 (상위 5개) 수집
        # #lowPrice_l 영역이 왼쪽 무료배송 섹션입니다.
        free_section = soup.select("#lowPrice_l .diff_item")
        for i, item in enumerate(free_section[:5], 1):
            price = item.select_one(".prc_c").text.strip() if item.select_one(".prc_c") else "0"
            # [날짜, 순위, 섹션명, 가격, 배송비정보]
            rows.append([now_str, f"{i}위", "무료배송섹션", price, "무료"])

        # 2. 유/무료 전체 섹션 (상위 5개) 수집
        # #lowPrice_r 영역이 오른쪽 전체 섹션입니다.
        all_section = soup.select("#lowPrice_r .diff_item")
        for i, item in enumerate(all_section[:5], 1):
            price = item.select_one(".prc_c").text.strip() if item.select_one(".prc_c") else "0"
            delivery = item.select_one(".delivery_base").text.strip() if item.select_one(".delivery_base") else "확인요망"
            # [날짜, 순위, 섹션명, 가격, 배송비정보]
            rows.append([now_str, f"{i}위", "전체섹션(유/무)", price, delivery])

        print(f"--- 수집 완료: 무료배송 {len(free_section[:5])}건 / 전체 {len(all_section[:5])}건 ---")

        # === 시트 저장 ===
        try:
            creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
            creds = json.loads(creds_raw)
            gc = gspread.service_account_from_dict(creds)
            
            sh = gc.open_by_key(SH_ID)
            wks = sh.get_worksheet(0)
            
            # 한 번에 10줄 추가
            wks.append_rows(rows)
            print("✅ 시트에 구분하여 저장 성공!")

        except Exception as e:
            print(f"❌ 저장 실패: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
