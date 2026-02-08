import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import gspread
import json
import os

# 기존 예시 ID 대신 판매자님의 실제 ID를 넣었습니다.
SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ"

async def get_danawa_data():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://prod.danawa.com/info/?pcode=13412984")
        await asyncio.sleep(7)
        
        soup = BeautifulSoup(await page.content(), 'html.parser')
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        rows = []

        # 데이터 수집
        items = soup.select(".diff_item")
        for i, item in enumerate(items[:10], 1):
            price = item.select_one(".prc_c").text.strip() if item.select_one(".prc_c") else "0"
            rows.append([now_str, f"{i}위", "다나와", price, "확인요망"])

        print(f"--- 수집 완료: {len(rows)}건 ---")

        # === 시트 저장 (단계별 확인) ===
        try:
            print("1. 인증 정보 읽는 중...")
            creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
            if not creds_raw:
                print("❌ 에러: GCP_CREDENTIALS가 비어있습니다.")
                return

            print("2. 구글 로그인 시도 중...")
            creds = json.loads(creds_raw)
            gc = gspread.service_account_from_dict(creds)
            
            print("3. 시트 파일 여는 중...")
            sh = gc.open_by_key(SH_ID)
            wks = sh.get_worksheet(0)
            
            print("4. 데이터 쓰는 중...")
            wks.append_rows(rows)
            print("✅ 최종 성공!")

        except Exception as e:
            # 에러의 상세 원인을 더 자세히 출력하도록 변경
            print(f"❌ 최종 실패 지점: {type(e).__name__}")
            print(f"❌ 상세 이유: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
