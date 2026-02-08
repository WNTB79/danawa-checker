import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import gspread
import json
import os

# 판매자님의 시트 ID
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
        
        # 데이터 로드 대기
        await asyncio.sleep(7)
        await page.evaluate("window.scrollTo(0, 1200)")
        await asyncio.sleep(3)

        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 오른쪽 섹션(#lowPrice_r) 타겟팅
        right_section = soup.select("#lowPrice_r .diff_item")
        
        if not right_section:
            all_items = soup.select(".diff_item")
            right_section = all_items[len(all_items)//2:] 

        rows = []
        # 최신 데이터가 위로 가도록 수집된 순서대로 리스트를 만듭니다.
        for i, item in enumerate(right_section[:5], 1):
            price_tag = item.select_one(".prc_c")
            if not price_tag: continue
            
            price = price_tag.get_text().replace(",", "").replace("원", "").strip()
            
            # 배송비 처리
            deliv_tag = item.select_one(".delivery_base")
            delivery = deliv_tag.get_text().strip() if deliv_tag else ""
            if "무료" not in delivery:
                delivery = "유료"
            
            rows.append([now_str, f"{i}위", "다나와", price, delivery])

        print(f"🔎 수집 완료: 다나와 TOP {len(rows)}건")

        # --- 구글 시트 저장 (상단 삽입) ---
        if rows:
            try:
                creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
                creds = json.loads(creds_raw)
                gc = gspread.service_account_from_dict(creds)
                sh = gc.open_by_key(SH_ID)
                wks = sh.get_worksheet(0)
                
                # [수정포인트] insert_rows를 사용하여 2행(제목줄 바로 아래)부터 데이터를 끼워 넣습니다.
                # rows 리스트를 그대로 넣으면 1위가 가장 위로 가게 됩니다.
                wks.insert_rows(rows, row=2)
                print("✅ 최신 데이터를 시트 상단(2행)에 삽입 성공!")
            except Exception as e:
                print(f"❌ 시트 저장 에러: {e}")
        else:
            print("❌ 수집 실패: 데이터를 찾지 못했습니다.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_
