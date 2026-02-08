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
        # 위장막 강화: 실제 Chrome과 유사한 인자 추가
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1024},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="ko-KR",
            timezone_id="Asia/Seoul"
        )
        page = await context.new_page()
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        final_matrix = [[now_str, f"{i}위"] for i in range(1, 6)]

        for idx, url in enumerate(URL_LIST, 1):
            try:
                print(f"🚀 {idx}개입 페이지 접속 중...")
                #referer를 추가하여 자연스러운 유입으로 위장
                await page.goto(url, wait_until="networkidle", timeout=60000)
                
                # 다나와 특유의 지연 로딩을 기다림
                await asyncio.sleep(10)
                
                # 화면을 아래로 천천히 내려서 가격표 로딩 유도
                for _ in range(3):
                    await page.mouse.wheel(0, 400)
                    await asyncio.sleep(1)

                # [디버깅용 스크린샷] 1번 구성만 찍어서 확인
                if idx == 1:
                    await page.screenshot(path="danawa_check.png")
                    print("📸 1개입 화면 스크린샷 저장 완료 (danawa_check.png)")

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # 선택자 범위를 아주 넓게 잡음 (클래스명 일부만 포함해도 수집)
                # '오른쪽 섹션'을 찾기 위해 .low_price, #lowPrice_r, .pay_comparison_list 등을 모두 뒤짐
                items = soup.select("#lowPrice_r .diff_item") or \
                        soup.select("div[class*='pay_comparison_list']:not([class*='free_delivery']) .diff_item") or \
                        soup.select(".diff_item")

                # 만약 여전히 0건이라면 왼쪽/오른쪽 구분 없이 일단 다 긁어와서 반으로 나눔 (오른쪽이 보통 뒤에 나옴)
                if not items:
                    all_items = soup.select(".diff_item")
                    if len(all_items) > 5:
                        items = all_items[len(all_items)//2:] 

                print(f"   ㄴ {idx}개입 데이터 발견: {len(items)}건")

                for i in range(5):
                    if i < len(items):
                        p_tag = items[i].select_one(".prc_c") or items[i].select_one(".price_sect em")
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
                print(f"✅ 데이터 삽입 성공!")
            except Exception as e:
                print(f"❌ 시트 오류: {e}")
        else:
            print("❌ 데이터 발견 실패. 스크린샷 확인이 필요합니다.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
