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
    "https://prod.danawa.com/info/?pcode=13412984",
    "https://prod.danawa.com/info/?pcode=13413059",
    "https://prod.danawa.com/info/?pcode=13413086",
    "https://prod.danawa.com/info/?pcode=13413254",
    "https://prod.danawa.com/info/?pcode=13678937",
    "https://prod.danawa.com/info/?pcode=13413314"
]

async def get_danawa_data():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080}, # 화면을 크게 넓혀서 좌우 구분을 확실히 함
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        final_matrix = [[now_str, f"{i}위"] for i in range(1, 6)]

        for idx, url in enumerate(URL_LIST, 1):
            try:
                print(f"🚀 {idx}개입 페이지 접속 중 (오른쪽 전용 추출)...")
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(8)
                
                # 확실한 로딩을 위해 하단으로 스크롤 후 잠시 대기
                await page.evaluate("window.scrollTo(0, 1200)")
                await asyncio.sleep(2)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # --- [핵심 수정] 오른쪽 섹션만 따로 떼어내기 ---
                # 'lowPrice_r'이라는 ID를 가진 div 섹션을 통째로 가져옵니다.
                right_section_html = soup.find('div', id='lowPrice_r')
                
                items = []
                if right_section_html:
                    # 잘라낸 오른쪽 섹션 안에서만 상품 리스트(.diff_item)를 찾습니다.
                    items = right_section_html.select(".diff_item")
                    print(f"   ㄴ [확인] 오른쪽 전용 섹션에서 {len(items)}건 발견")
                else:
                    # 만약 ID가 없다면 클래스명으로 다시 시도
                    right_area = soup.select_one(".pay_comparison_list:not(.free_delivery)")
                    if right_area:
                        items = right_area.select(".diff_item")
                        print(f"   ㄴ [보조] 유료배송 섹션에서 {len(items)}건 발견")

                for i in range(5):
                    if i < len(items):
                        # 가격 태그 추출
                        p_tag = items[i].select_one(".prc_c")
                        price = p_tag.get_text().replace(",", "").replace("원", "").strip() if p_tag else "0"
                        final_matrix[i].append(price)
                    else:
                        final_matrix[i].append("-")

            except Exception as e:
                print(f"⚠️ {idx}개입 에러: {e}")
                for i in range(5): final_matrix[i].append("-")

        # --- 저장 로직 ---
        has_data = any(row[2] != "-" for row in final_matrix)
        if has_data:
            try:
                creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
                creds = json.loads(creds_raw)
                gc = gspread.service_account_from_dict(creds)
                sh = gc.open_by_key(SH_ID)
                wks = sh.get_worksheet(0)
                wks.insert_rows(final_matrix, row=2)
                print(f"✅ 오른쪽 섹션 데이터만 선별하여 삽입 완료!")
            except Exception as e:
                print(f"❌ 시트 오류: {e}")
        else:
            print("❌ 오른쪽 섹션 추출 실패")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
