import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import gspread
import json
import os

SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ" 
MAX_ROWS = 10000

# 제공해주신 구성별 URL 리스트
URL_LIST = [
    "https://prod.danawa.com/info/?pcode=13412984", # 1개입
    "https://prod.danawa.com/info/?pcode=13413059", # 2개입
    "https://prod.danawa.com/info/?pcode=13413086", # 3개입
    "https://prod.danawa.com/info/?pcode=13413254", # 4개입
    "https://prod.danawa.com/info/?pcode=13678937", # 5개입
    "https://prod.danawa.com/info/?pcode=13413314"  # 6개입
]

async def get_danawa_data():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # 결과 매트릭스 초기화 (5행 x 8열: 날짜, 순위, 1~6개입 가격)
        final_matrix = [[now_str, f"{i}위"] for i in range(1, 6)]

        # 구성별 주소를 직접 순회하며 수집
        for idx, url in enumerate(URL_LIST, 1):
            try:
                print(f"🚀 {idx}개입 페이지 접속 중...")
                await page.goto(url, wait_until="load", timeout=60000)
                # 다나와 보안 감지를 피하고 렌더링을 기다리기 위한 충분한 대기
                await asyncio.sleep(8) 
                
                # 데이터 활성화를 위한 스크롤
                await page.evaluate("window.scrollTo(0, 1100)")
                await asyncio.sleep(2)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # 우측 가격 비교 리스트 추출 (다양한 선택자 대응)
                items = soup.select("#lowPrice_r .diff_item") or \
                        soup.select(".pay_comparison_list:not(.free_delivery) .diff_item") or \
                        soup.select(".diff_item")

                print(f"   ㄴ {idx}개입 데이터 발견: {len(items)}건")

                for i in range(5):
                    if i < len(items):
                        p_tag = items[i].select_one(".prc_c")
                        price = p_tag.get_text().replace(",", "").replace("원", "").strip() if p_tag else "0"
                        final_matrix[i].append(price)
                    else:
                        final_matrix[i].append("-")

            except Exception as e:
                print(f"⚠️ {idx}개입 수집 에러: {e}")
                for i in range(5): final_matrix[i].append("-")

        # --- 구글 시트 저장 ---
        # 실제 가격 데이터가 하나라도 들어있는지 확인 (3번째 열부터 가격)
        has_data = any(row[2] != "-" for row in final_matrix)
        
        if has_data:
            try:
                creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
                creds = json.loads(creds_raw)
                gc = gspread.service_account_from_dict(creds)
                sh = gc.open_by_key(SH_ID)
                wks = sh.get_worksheet(0)
                
                # 가로로 완성된 5줄을 한꺼번에 시트 상단(2행)에 삽입
                wks.insert_rows(final_matrix, row=2)
                print(f"✅ [성공] {now_str} 기준 가로형 데이터 삽입 완료!")

                # 행 개수 관리 (3달치 유지)
                total_rows = len(wks.get_all_values())
                if total_rows > MAX_ROWS:
                    wks.delete_rows(MAX_ROWS + 1, total_rows)
            except Exception as e:
                print(f"❌ 시트 저장 실패: {e}")
        else:
            print("❌ 수집된 데이터가 하나도 없습니다. 페이지 구조 또는 차단 여부를 확인하세요.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
