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
                print(f"🚀 {idx}개입 페이지 분석 중 (최종 수단)...")
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(12) # 로딩 시간 대폭 연장
                
                # 강제 스크롤로 데이터 활성화
                await page.evaluate("window.scrollTo(0, 1500)")
                await asyncio.sleep(3)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # 1. 모든 상품 리스트를 가져옵니다 (li 또는 div 단위)
                # 다나와 가격비교 리스트의 공통적인 속성을 모두 뒤집니다.
                items = soup.select(".diff_item, .product-item, li[id^='productItem']")
                
                right_items = []
                for item in items:
                    all_text = item.get_text(separator=' ', strip=True)
                    
                    # 2. [필터링 법칙]
                    # - '무료배송' 글자가 없어야 함
                    # - '배송비' 또는 '원' 글자가 있어야 함
                    # - 숫자가 포함된 가격 정보가 있어야 함
                    if "무료배송" not in all_text and ("배송비" in all_text or "별도" in all_text):
                        price_tag = item.select_one(".prc_c, .price")
                        if price_tag:
                            right_items.append(item)

                print(f"   ㄴ [결과] 유료배송 후보 {len(right_items)}건 발견")

                for i in range(5):
                    if i < len(right_items):
                        p_tag = right_items[i].select_one(".prc_c, .price")
                        # 숫자만 남기고 제거
                        raw_price = p_tag.get_text()
                        price = "".join(filter(str.isdigit, raw_price))
                        final_matrix[i].append(price if price else "0")
                    else:
                        final_matrix[i].append("-")

            except Exception as e:
                print(f"⚠️ {idx}개입 에러: {e}")
                for i in range(5): final_matrix[i].append("-")

        # --- 저장부 ---
        has_data = any(row[2] != "-" and row[2] != "0" for row in final_matrix)
        if has_data:
            try:
                creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
                creds = json.loads(creds_raw)
                gc = gspread.service_account_from_dict(creds)
                sh = gc.open_by_key(SH_ID)
                wks = sh.get_worksheet(0)
                wks.insert_rows(final_matrix, row=2)
                print(f"✅ 드디어 성공! 시트를 확인하세요.")
            except Exception as e:
                print(f"❌ 저장 오류: {e}")
        else:
            print("❌ 이번에도 실패했습니다. 다나와가 로봇 전용 가짜 페이지를 보여주는 것 같습니다.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
