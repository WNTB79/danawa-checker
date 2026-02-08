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
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        final_matrix = [[now_str, f"{i}위"] for i in range(1, 6)]

        for idx, url in enumerate(URL_LIST, 1):
            try:
                print(f"🚀 {idx}개입 페이지 분석 중 (배송비 문구 필터링)...")
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(10)
                
                await page.evaluate("window.scrollTo(0, 1100)")
                await asyncio.sleep(3)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # 모든 상품 항목(.diff_item)을 가져옵니다.
                all_items = soup.select(".diff_item")
                
                # --- [핵심 로직] 배송비 텍스트 조건부 필터링 ---
                right_items = []
                for item in all_items:
                    # 배송비 정보가 적힌 태그 찾기
                    delivery_info = item.select_one(".delivery_base")
                    delivery_text = delivery_info.get_text() if delivery_info else ""
                    
                    # 1. "무료"라는 단어가 없고
                    # 2. "배송비" 또는 "원" 이라는 단어가 포함된 경우만 오른쪽 섹션으로 간주
                    if "무료" not in delivery_text and ("배송비" in delivery_text or "원" in delivery_text):
                        right_items.append(item)

                print(f"   ㄴ [필터링 결과] 유료배송 상품 {len(right_items)}건 발견")

                for i in range(5):
                    if i < len(right_items):
                        p_tag = right_items[i].select_one(".prc_c")
                        price = p_tag.get_text().replace(",", "").replace("원", "").strip() if p_tag else "0"
                        final_matrix[i].append(price)
                    else:
                        final_matrix[i].append("-")

            except Exception as e:
                print(f"⚠️ {idx}개입 에러: {e}")
                for i in range(5): final_matrix[i].append("-")

        # --- 구글 시트 저장 ---
        has_data = any(row[2] != "-" for row in final_matrix)
        if has_data:
            try:
                creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
                creds = json.loads(creds_raw)
                gc = gspread.service_account_from_dict(creds)
                sh = gc.open_by_key(SH_ID)
                wks = sh.get_worksheet(0)
                wks.insert_rows(final_matrix, row=2)
                print(f"✅ 유료배송 데이터만 정확히 골라내어 기록했습니다!")
            except Exception as e:
                print(f"❌ 시트 오류: {e}")
        else:
            print("❌ 조건에 맞는 (유료배송) 데이터를 찾지 못했습니다.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
