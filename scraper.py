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
        
        # 1. 페이지 접속 및 충분한 대기
        await page.goto("https://prod.danawa.com/info/?pcode=13412984", wait_until="networkidle")
        await asyncio.sleep(8) # 로딩 시간을 조금 더 늘렸습니다.
        
        # 2. 가격 비교 섹션이 보일 때까지 아래로 스크롤
        await page.mouse.wheel(0, 1500)
        await asyncio.sleep(3)

        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        rows = []

        # --- 데이터 추출 로직 시작 ---
        
        # [방법 1] ID 기반 추출 시도
        free_section = soup.select("#lowPrice_l .diff_item")
        all_section = soup.select("#lowPrice_r .diff_item")

        # [방법 2] ID로 못 찾을 경우 클래스 기반 통합 추출 후 분류
        if not free_section and not all_section:
            print("⚠️ ID 기반 탐색 실패. 클래스 기반으로 재시도합니다.")
            items = soup.select(".diff_item")
            # 배송비 텍스트에 '무료배송'이 포함된 것과 아닌 것을 분리
            free_section = [i for i in items if i.select_one(".delivery_base") and "무료" in i.select_one(".delivery_base").text]
            all_section = items # 전체 섹션은 모든 아이템

        # 1. 무료배송 섹션 5개 정리
        for i, item in enumerate(free_section[:5], 1):
            price = item.select_one(".prc_c").text.replace(",", "").replace("원", "").strip() if item.select_one(".prc_c") else "0"
            rows.append([now_str, f"{i}위", "무료배송섹션", price, "무료"])

        # 2. 전체 섹션 5개 정리
        for i, item in enumerate(all_section[:5], 1):
            price = item.select_one(".prc_c").text.replace(",", "").replace("원", "").strip() if item.select_one(".prc_c") else "0"
            delivery = item.select_one(".delivery_base").text.strip() if item.select_one(".delivery_base") else "별도"
            rows.append([now_str, f"{i}위", "전체섹션(유/무)", price, delivery])

        # --- 데이터 추출 로직 끝 ---

        print(f"--- 수집 결과: 무료 {len(free_section[:5])}건 / 전체 {len(all_section[:5])}건 ---")

        if not rows:
            print("❌ 최종적으로 수집된 데이터가 없습니다. 페이지 구조를 확인해야 합니다.")
            await browser.close()
            return

        try:
            creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
            creds = json.loads(creds_raw)
            gc = gspread.service_account_from_dict(creds)
            sh = gc.open_by_key(SH_ID)
            wks = sh.get_worksheet(0)
            wks.append_rows(rows)
            print("✅ 시트 저장 완료!")
        except Exception as e:
            print(f"❌ 시트 저장 에러: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
