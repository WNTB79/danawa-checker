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
        
        print("🔗 다나와 접속 중...")
        # 대기 시간을 늘리고 네트워크 안정화 대기
        await page.goto("https://prod.danawa.com/info/?pcode=13412984", wait_until="load", timeout=60000)
        await asyncio.sleep(10) # 전체 로딩을 위해 충분히 대기

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # 결과 매트릭스 초기화 (5행 x 8열: 날짜, 순위, 1~6개입 가격)
        final_matrix = []
        for i in range(1, 6):
            final_matrix.append([now_str, f"{i}위"])

        # 1개입부터 6개입까지 수집 시도
        for idx in range(1, 7):
            try:
                # '다른 구성' 내의 버튼을 텍스트나 순서로 직접 타겟팅
                # 예: .other_conf_list 내의 첫 번째, 두 번째... li 태그
                btn_selector = f"//div[contains(@class, 'other_conf')]//li[{idx}]//a"
                
                exists = await page.query_selector(btn_selector)
                if exists:
                    print(f"📦 {idx}개입 구성 클릭...")
                    await page.click(btn_selector)
                    await asyncio.sleep(5)
                else:
                    print(f"⚠️ {idx}개입 버튼 없음 (또는 1개입 기본 화면)")

                # 스크롤해서 리스트 갱신 유도
                await page.evaluate("window.scrollTo(0, 1000)")
                await asyncio.sleep(2)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # 우측 가격 비교 리스트의 아이템들 추출
                items = soup.select("#lowPrice_r .diff_item")
                if not items: # 보조 선택자
                    items = soup.select(".pay_comparison_list.free_delivery .diff_item") or soup.select(".pay_comparison_list .diff_item")

                # 5위까지 가격 정보를 매트릭스에 추가
                for i in range(5):
                    if i < len(items):
                        p_tag = items[i].select_one(".prc_c")
                        price = p_tag.get_text().replace(",", "").replace("원", "").strip() if p_tag else "0"
                        final_matrix[i].append(price)
                    else:
                        final_matrix[i].append("-") # 데이터 부족 시 대시 표기

            except Exception as e:
                print(f"⚠️ {idx}개입 처리 중 에러: {e}")
                for i in range(5):
                    final_matrix[i].append("-")

        # --- 데이터 검증 및 저장 ---
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
                print(f"✅ 가로형 데이터 삽입 완료! (날짜: {now_str})")

                # 행 관리
                total_rows = len(wks.get_all_values())
                if total_rows > MAX_ROWS:
                    wks.delete_rows(MAX_ROWS + 1, total_rows)
            except Exception as e:
                print(f"❌ 시트 저장 실패: {e}")
        else:
            print("❌ 수집된 데이터가 전혀 없습니다. 페이지 구조 확인이 필요합니다.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
