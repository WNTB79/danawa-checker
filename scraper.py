import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import gspread
import json
import os

SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ" 

async def get_danawa_data():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print("🔗 다나와 접속 및 TOP 5 수집 시작...")
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

        # --- 가격 변동 체크 로직 ---
        try:
            creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
            creds = json.loads(creds_raw)
            gc = gspread.service_account_from_dict(creds)
            sh = gc.open_by_key(SH_ID)
            wks = sh.get_worksheet(0)
            
            # 기존 시트의 2행 4열(이전 1위 가격)을 가져옵니다.
            # 데이터가 하나도 없을 경우를 대비해 예외처리 합니다.
            try:
                prev_first_price = int(wks.cell(2, 4).value.replace(",", ""))
            except:
                prev_first_price = 0
        except Exception as e:
            print(f"⚠️ 이전 데이터 읽기 실패 (첫 실행으로 간주): {e}")
            prev_first_price = 0

        rows = []
        for i, item in enumerate(right_section[:5], 1):
            price_tag = item.select_one(".prc_c")
            if not price_tag: continue
            
            current_price = int(price_tag.get_text().replace(",", "").replace("원", "").strip())
            
            # 배송비 처리
            deliv_tag = item.select_one(".delivery_base")
            delivery = deliv_tag.get_text().strip() if deliv_tag else ""
            if "무료" not in delivery:
                delivery = "유료"
            
            # 변동 사항 계산 (1위에 대해서만 수행)
            change_text = ""
            if i == 1 and prev_first_price != 0:
                diff = current_price - prev_first_price
                if diff > 0:
                    change_text = f"▲ {diff:,}원 상승"
                elif diff < 0:
                    change_text = f"▼ {abs(diff):,}원 하락"
                # 변동이 0원일 때는 빈칸 유지

            # [날짜, 순위, 플랫폼, 가격, 배송비, 변동]
            rows.append([now_str, f"{i}위", "다나와", current_price, delivery, change_text])

        # --- 구글 시트 저장 (상단 삽입) ---
        if rows:
            try:
                wks.insert_rows(rows, row=2)
                print("✅ 최신 데이터 및 변동 사항 삽입 성공!")
            except Exception as e:
                print(f"❌ 시트 저장 에러: {e}")
        else:
            print("❌ 수집 실패")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
