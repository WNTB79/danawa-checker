import asyncio
import random  # 랜덤 대기를 위해 추가
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
    # --- [차단 방지] 0초 ~ 1200초(20분) 사이 랜덤 대기 ---
    wait_sec = random.randint(0, 1200)
    print(f"🕒 차단 방지를 위해 {wait_sec // 60}분 {wait_sec % 60}초 동안 대기 후 시작합니다...")
    await asyncio.sleep(wait_sec)
    # --------------------------------------------------

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # 실제 데이터 수집 시점의 시간 기록
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        final_matrix = [[now_str, f"{i}위"] for i in range(1, 6)]

        for idx, url in enumerate(URL_LIST, 1):
            try:
                print(f"🚀 {idx}개입 페이지 분석 중... (시각: {datetime.now().strftime('%H:%M:%S')})")
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(10)
                
                await page.evaluate("window.scrollTo(0, 1500)")
                await asyncio.sleep(5)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                items = soup.select(".diff_item, .product-item, li[id^='productItem']")
                
                right_items = []
                for item in items:
                    all_text = item.get_text(separator=' ', strip=True)
                    # 유료배송 섹션 필터링 로직 (성공했던 로직 유지)
                    if "무료배송" not in all_text and ("배송비" in all_text or "별도" in all_text or "원" in all_text):
                        price_tag = item.select_one(".prc_c, .price")
                        if price_tag:
                            right_items.append(item)

                for i in range(5):
                    if i < len(right_items):
                        p_tag = right_items[i].select_one(".prc_c, .price")
                        raw_price = p_tag.get_text()
                        price = "".join(filter(str.isdigit, raw_price))
                        final_matrix[i].append(price if price else "0")
                    else:
                        final_matrix[i].append("-")

            except Exception as e:
                print(f"⚠️ {idx}개입 에러: {e}")
                for i in range(5): final_matrix[i].append("-")

        # --- 저장 로직 ---
        has_data = any(row[2] != "-" and row[2] != "0" for row in final_matrix)
        if has_data:
            try:
                creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
                creds = json.loads(creds_raw)
                gc = gspread.service_account_from_dict(creds)
                sh = gc.open_by_key(SH_ID)
                wks = sh.get_worksheet(0)
                wks.insert_rows(final_matrix, row=2)
                print(f"✅ 데이터 저장 완료! (수집시각: {now_str})")
            except Exception as e:
                print(f"❌ 시트 저장 실패: {e}")
        else:
            print("❌ 수집된 데이터가 없어 저장하지 않았습니다.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
