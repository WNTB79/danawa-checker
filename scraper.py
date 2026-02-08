import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import gspread
import json
import os

SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ" 
MAX_ROWS = 10000

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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Korea) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        final_matrix = [[now_str, f"{i}위"] for i in range(1, 6)]

        for idx, url in enumerate(URL_LIST, 1):
            try:
                print(f"🚀 {idx}개입 페이지 접속 중 (오른쪽 섹션 추출)...")
                await page.goto(url, wait_until="load", timeout=60000)
                await asyncio.sleep(8) 
                
                # 오른쪽 섹션이 로드되도록 확실하게 스크롤
                await page.evaluate("window.scrollTo(0, 1100)")
                await asyncio.sleep(2)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # --- [핵심 수정] 오직 오른쪽 섹션(#lowPrice_r) 안에 있는 아이템만 가져옵니다 ---
                # 만약 ID가 안 잡힐 경우를 대비해 '배송비 유료/무료 전체' 클래스명을 명시
                right_area = soup.select("#lowPrice_r .diff_item")
                
                if not right_area:
                    # 다나와 레이아웃 변화 대응: 무료배송이 아닌(not .free_delivery) 가격비교 리스트 타겟팅
                    right_area = soup.select(".pay_comparison_list:not(.free_delivery) .diff_item")

                print(f"   ㄴ {idx}개입 오른쪽 데이터 발견: {len(right_area)}건")

                for i in range(5):
                    if i < len(right_area):
                        # 해당 아이템 내의 가격 태그만 추출
                        p_tag = right_area[i].select_one(".prc_c")
                        price = p_tag.get_text().replace(",", "").replace("원", "").strip() if p_tag else "0"
                        final_matrix[i].append(price)
                    else:
                        final_matrix[i].append("-")

            except Exception as e:
                print(f"⚠️ {idx}개입 수집 에러: {e}")
                for i in range(5): final_matrix[i].append("-")

        # --- 데이터 저장 ---
        # 실제 가격 데이터가 하나라도 들어있는지 확인
        has_data = any(row[2] != "-" for row in final_matrix)
        
        if has_data:
            try:
                creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
                creds = json.loads(creds_raw)
                gc = gspread.service_account_from_dict(creds)
                sh = gc.open_by_key(SH_ID)
                wks = sh.get_worksheet(0)
                
                wks.insert_rows(final_matrix, row=2)
                print(f"✅ [성공] 오른쪽 섹션(유/무료 전체) 데이터 삽입 완료!")

                total_rows = len(wks.get_all_values())
                if total_rows > MAX_ROWS:
                    wks.delete_rows(MAX_ROWS + 1, total_rows)
            except Exception as e:
                print(f"❌ 시트 저장 실패: {e}")
        else:
            print("❌ 오른쪽 섹션 데이터를 찾지 못했습니다.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
