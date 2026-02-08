import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import gspread
import json
import os

SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ" 
MAX_ROWS = 11000  # 3달치 데이터 유지 (24시간 * 90일 * 5행 = 약 10,800행)

async def get_danawa_data():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print("🔗 다나와 접속 및 데이터 수집 중...")
        await page.goto("https://prod.danawa.com/info/?pcode=13412984", wait_until="load")
        
        await asyncio.sleep(7)
        await page.evaluate("window.scrollTo(0, 1200)")
        await asyncio.sleep(3)

        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        right_section = soup.select("#lowPrice_r .diff_item")
        if not right_section:
            all_items = soup.select(".diff_item")
            right_section = all_items[len(all_items)//2:] 

        # --- 구글 시트 연결 및 이전 가격 확인 ---
        try:
            creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
            creds = json.loads(creds_raw)
            gc = gspread.service_account_from_dict(creds)
            sh = gc.open_by_key(SH_ID)
            wks = sh.get_worksheet(0)
            
            try:
                # 2행 4열(이전 1위 가격) 확인
                prev_val = wks.cell(2, 4).value
                prev_first_price = int(prev_val.replace(",", "")) if prev_val else 0
            except:
                prev_first_price = 0
        except Exception as e:
            print(f"⚠️ 시트 연결 실패: {e}")
            prev_first_price = 0

        rows = []
        for i, item in enumerate(right_section[:5], 1):
            price_tag = item.select_one(".prc_c")
            if not price_tag: continue
            
            current_price = int(price_tag.get_text().replace(",", "").replace("원", "").strip())
            
            deliv_tag = item.select_one(".delivery_base")
            delivery = deliv_tag.get_text().strip() if deliv_tag else ""
            if "무료" not in delivery:
                delivery = "유료"
            
            # 가격 변동 계산
            change_text = ""
            if i == 1 and prev_first_price != 0:
                diff = current_price - prev_first_price
                if diff > 0:
                    change_text = f"▲ {diff:,}원 상승"
                elif diff < 0:
                    change_text = f"▼ {abs(diff):,}원 하락"

            rows.append([now_str, f"{i}위", "다나와", current_price, delivery, change_text])

        # --- 데이터 저장 및 오래된 데이터 삭제 로직 ---
        if rows:
            try:
                # 1. 최신 데이터 상단 삽입
                wks.insert_rows(rows, row=2)
                print(f"✅ 최신 데이터 5건 삽입 완료.")

                # 2. 전체 행 개수 확인 후 삭제
                # row_count는 데이터가 들어있는 행의 개수를 의미합니다.
                total_rows = len(wks.get_all_values())
                if total_rows > MAX_ROWS:
                    # MAX_ROWS 이후부터 끝까지 삭제
                    # 가령 11,005행이 되었다면, 11,001행부터 5개 행을 삭제
                    wks.delete_rows(MAX_ROWS + 1, total_rows)
                    print(f"🗑️ 3달치 초과 데이터 자동 삭제 완료 (현재 {total_rows}행)")
                
            except Exception as e:
                print(f"❌ 시트 작업 중 오류: {e}")
        else:
            print("❌ 수집된 데이터가 없습니다.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
