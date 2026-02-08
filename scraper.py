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
        
        print("🔗 다나와 접속 및 오른쪽 섹션(TOP 5) 로딩 중...")
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
        
        # ID로 못 찾을 경우를 대비한 백업 로직
        if not right_section:
            all_items = soup.select(".diff_item")
            right_section = all_items[len(all_items)//2:] 

        rows = []
        # 정확히 5개만 추출
        for i, item in enumerate(right_section[:5], 1):
            price_tag = item.select_one(".prc_c")
            if not price_tag: continue
            
            price = price_tag.get_text().replace(",", "").replace("원", "").strip()
            deliv_tag = item.select_one(".delivery_base")
            delivery = deliv_tag.get_text().strip() if deliv_tag else "별도"
            
            # [날짜, 순위, 섹션, 가격, 배송비]
            rows.append([now_str, f"{i}위", "오른쪽_전체섹션", price, delivery])

        print(f"🔎 수집 완료: 오른쪽 섹션 상위 {len(rows)}건")

        # --- 구글 시트 저장 ---
        if rows:
            try:
                creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
                creds = json.loads(creds_raw)
                gc = gspread.service_account_from_dict(creds)
                sh = gc.open_by_key(SH_ID)
                wks = sh.get_worksheet(0)
                
                wks.append_rows(rows)
                print("✅ 시트 저장 성공!")
            except Exception as e:
                print(f"❌ 시트 저장 에러: {e}")
        else:
            print("❌ 수집 실패: 데이터를 찾지 못했습니다.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
