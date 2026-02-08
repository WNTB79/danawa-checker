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
        # 1. 브라우저 잠입 설정 강화
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="ko-KR"
        )
        page = await context.new_page()
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        final_matrix = [[now_str, f"{i}위"] for i in range(1, 6)]

        for idx, url in enumerate(URL_LIST, 1):
            try:
                print(f"🚀 {idx}개입 페이지 접속 시도...")
                # 페이지 로드 타임아웃 넉넉히 설정
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # 2. 오른쪽 섹션(#lowPrice_r)이 나타날 때까지 강제 대기 (최대 15초)
                try:
                    await page.wait_for_selector("#lowPrice_r", timeout=15000)
                except:
                    print(f"   ⚠️ {idx}개입: 오른쪽 섹션 로딩 지연 중... 강제 수집 시도")

                # 데이터 활성화를 위해 여러 번 스크롤
                await page.mouse.wheel(0, 1000)
                await asyncio.sleep(3)
                await page.mouse.wheel(0, 500)
                await asyncio.sleep(2)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # 3. 오른쪽 영역 특정 (여러 방법 동원)
                # 방법 A: ID로 찾기
                right_area = soup.select("#lowPrice_r .diff_item")
                
                # 방법 B: ID가 없을 경우, "배송비 포함" 혹은 "유료" 섹션 찾기
                if not right_area:
                    # '무료배송' 클래스가 없는 가격비교 그룹 찾기
                    sections = soup.select(".pay_comparison_list")
                    for sec in sections:
                        if "free_delivery" not in sec.get("class", []):
                            right_area = sec.select(".diff_item")
                            break

                print(f"   ㄴ {idx}개입 데이터 발견: {len(right_area)}건")

                for i in range(5):
                    if i < len(right_area):
                        p_tag = right_area[i].select_one(".prc_c")
                        price = p_tag.get_text().replace(",", "").replace("원", "").strip() if p_tag else "0"
                        final_matrix[i].append(price)
                    else:
                        final_matrix[i].append("-")

            except Exception as e:
                print(f"⚠️ {idx}개입 치명적 에러: {e}")
                for i in range(5): final_matrix[i].append("-")

        # --- 데이터 저장부 ---
        has_data = any(row[2] != "-" for row in final_matrix)
        
        if has_data:
            try:
                creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
                creds = json.loads(creds_raw)
                gc = gspread.service_account_from_dict(creds)
                sh = gc.open_by_key(SH_ID)
                wks = sh.get_worksheet(0)
                
                wks.insert_rows(final_matrix, row=2)
                print(f"✅ [성공] {now_str} 데이터가 시트에 기록되었습니다!")
            except Exception as e:
                print(f"❌ 시트 저장 실패: {e}")
        else:
            print("❌ 모든 시도 실패: 다나와가 접속을 차단했거나 화면 구조가 완전히 바뀌었습니다.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
