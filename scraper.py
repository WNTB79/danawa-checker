import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import gspread
import json
import os

SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ" 
MAX_ROWS = 10000

async def get_danawa_data():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print("🔗 다나와 접속 및 가로형 수집 시작...")
        # 접속 후 페이지가 완전히 로드될 때까지 기다림
        await page.goto("https://prod.danawa.com/info/?pcode=13412984", wait_until="networkidle")
        await asyncio.sleep(5)

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        final_matrix = [[now_str, f"{i}위"] for i in range(1, 6)]

        # 1. '다른 구성' 버튼들을 모두 찾아옵니다.
        # 클래스명이 바뀌어도 '다른 구성' 영역 내의 li 태그들을 찾도록 수정
        buttons = await page.query_selector_all(".other_conf_list li a, .diff_conf_tab li a")
        
        if not buttons:
            print("⚠️ 버튼을 찾지 못해 기본 리스트만 수집합니다.")
            # 버튼을 못 찾아도 현재 보이는 화면이라도 수집하도록 예외처리
            buttons = [None] # 루프를 최소 한 번은 돌게 함

        # 최대 6개까지만 순회
        for idx in range(6):
            try:
                if idx < len(buttons) and buttons[idx] is not None:
                    print(f"📦 {idx+1}개입 버튼 클릭 중...")
                    await buttons[idx].click()
                    await asyncio.sleep(4)
                
                # 스크롤해서 가격표 활성화
                await page.evaluate("window.scrollTo(0, 1000)")
                await asyncio.sleep(2)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # 가격 비교 리스트 추출 (ID나 클래스 중 걸리는 것으로)
                items = soup.select("#lowPrice_r .diff_item, .pay_comparison_list .diff_item")

                for i in range(5):
                    if i < len(items):
                        price_tag = items[i].select_one(".prc_c")
                        price = price_tag.get_text().replace(",", "").replace("원", "").strip() if price_tag else "0"
                    else:
                        price = "-"
                    final_matrix[i].append(price)

            except Exception as e:
                print(f"⚠️ {idx+1}번 구성 수집 중 에러: {e}")
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
                
                wks.insert_rows(final_matrix, row=2)
                print(f"✅ 가로형 데이터({len(buttons)}개 구성) 삽입 완료!")

                total_rows = len(wks.get_all_values())
                if total_rows > MAX_ROWS:
                    wks.delete_rows(MAX_ROWS + 1, total_rows)
            except Exception as e:
                print(f"❌ 저장 에러: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
