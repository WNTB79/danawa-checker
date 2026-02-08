import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import gspread
import json
import os

SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ" 
MAX_ROWS = 10000 # 가로형은 행을 적게 쓰므로 1만 행이면 충분히 오래 보관합니다.

async def get_danawa_data():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print("🔗 다나와 접속 및 가로형 수집 시작...")
        await page.goto("https://prod.danawa.com/info/?pcode=13412984", wait_until="load")
        await asyncio.sleep(5)

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 각 순위별(1~5위)로 구성별 가격을 담을 리스트 (5줄 생성용)
        # 구성: [ [1위줄], [2위줄], [3위줄], [4위줄], [5위줄] ]
        final_matrix = [[now_str, f"{i}위"] for i in range(1, 6)]

        # 1개입부터 6개입까지 순회
        for bundle_idx in range(1, 7):
            try:
                print(f"📦 {bundle_idx}개입 클릭 중...")
                button_selector = f".other_conf_list li:nth-child({bundle_idx}) a"
                await page.wait_for_selector(button_selector, timeout=5000)
                await page.click(button_selector)
                await asyncio.sleep(4)

                await page.evaluate("window.scrollTo(0, 1500)")
                await asyncio.sleep(2)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                items = soup.select("#lowPrice_r .diff_item")
                if not items:
                    items = soup.select(".pay_comparison_list:not(.free_delivery) .diff_item")

                # 각 순위별로 가격을 해당 행에 추가
                for i in range(5):
                    if i < len(items):
                        price_tag = items[i].select_one(".prc_c")
                        price = price_tag.get_text().replace(",", "").replace("원", "").strip() if price_tag else "0"
                    else:
                        price = "-" # 데이터가 없을 경우
                    
                    final_matrix[i].append(price)

            except Exception as e:
                print(f"⚠️ {bundle_idx}개입 수집 실패: {e}")
                # 실패 시 빈 칸 채우기
                for i in range(5):
                    final_matrix[i].append("-")

        # --- 구글 시트 저장 ---
        if final_matrix:
            try:
                creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
                creds = json.loads(creds_raw)
                gc = gspread.service_account_from_dict(creds)
                sh = gc.open_by_key(SH_ID)
                wks = sh.get_worksheet(0)
                
                # 가로로 완성된 5줄을 시트 상단에 삽입
                wks.insert_rows(final_matrix, row=2)
                print(f"✅ 가로형 데이터 수집 및 삽입 완료!")

                # 초과 행 삭제
                total_rows = len(wks.get_all_values())
                if total_rows > MAX_ROWS:
                    wks.delete_rows(MAX_ROWS + 1, total_rows)
            except Exception as e:
                print(f"❌ 저장 에러: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
