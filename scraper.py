import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import gspread
import json
import os

# === [수정] 본인의 시트 ID를 다시 한번 정확히 넣어주세요 ===
SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ" # 예시입니다. 본인 것으로 교체!
# =====================================================

async def get_danawa_data():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        await page.goto("https://prod.danawa.com/info/?pcode=13412984", wait_until="domcontentloaded")
        await asyncio.sleep(6) # 로딩 대기시간 소폭 증가
        await page.mouse.wheel(0, 1000)
        await asyncio.sleep(3)

        soup = BeautifulSoup(await page.content(), 'html.parser')
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        rows = []

        # 데이터 수집 (로그 확인용)
        free_items = soup.select("#lowPrice_l .diff_item") or [i for i in soup.select(".diff_item") if "무료배송" in i.get_text()]
        for i, item in enumerate(free_items[:5], 1):
            price = item.select_one(".prc_c").text.strip() if item.select_one(".prc_c") else "0"
            rows.append([now_str, f"무료 {i}위", "다나와", price, "무료배송"])

        all_items = soup.select("#lowPrice_r .diff_item") or soup.select(".diff_item")
        for i, item in enumerate(all_items[:5], 1):
            price = item.select_one(".prc_c").text.strip() if item.select_one(".prc_c") else "0"
            delivery = item.select_one(".delivery_base").text.strip() if item.select_one(".delivery_base") else "별도"
            rows.append([now_str, f"전체 {i}위", "다나와", price, delivery])

        # === 시트 저장 로직 (에러 출력 강화) ===
        try:
            creds_json = os.environ.get('GCP_CREDENTIALS')
            if not creds_json:
                print("❌ 에러: GitHub Secret 'GCP_CREDENTIALS'를 찾을 수 없습니다.")
                return

            creds = json.loads(creds_json)
            gc = gspread.service_account_from_dict(creds)
            
            # 시트 열기 시도
            sh = gc.open_by_key(SH_ID)
            # '시트1'이라는 이름의 탭이 없을 경우를 대비해 첫 번째 탭을 직접 가져옴
            worksheet = sh.get_worksheet(0) 
            
            if rows:
                worksheet.append_rows(rows)
                print(f"✅ 성공: {len(rows)}개의 데이터를 시트에 저장했습니다!")
            else:
                print("⚠️ 경고: 수집된 데이터가 없어 저장하지 않았습니다.")

        except Exception as e:
            print(f"❌ 시트 저장 실패 상세 원인: {str(e)}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
