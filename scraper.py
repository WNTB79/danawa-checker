import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import gspread
import json
import os

# === [수정 포인트] 여기에 본인의 구글 시트 ID를 넣으세요 ===
SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ" 
# =====================================================

async def get_danawa_data():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        url = "https://prod.danawa.com/info/?pcode=13412984"
        await page.goto(url, wait_until="domcontentloaded")
        
        await asyncio.sleep(5)
        await page.mouse.wheel(0, 1000)
        await asyncio.sleep(3)

        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n===== 수집 시간(KST): {now_str} =====")

        # 시트에 저장할 데이터를 담을 리스트
        rows = []

        # 1. 무료배송 섹션 수집
        free_items = soup.select("#lowPrice_l .diff_item") or [i for i in soup.select(".diff_item") if "무료배송" in i.get_text()]
        for i, item in enumerate(free_items[:5], 1):
            price = item.select_one(".prc_c").text.strip() if item.select_one(".prc_c") else "0"
            rows.append([now_str, "무료배송", f"{i}위", price])
            print(f"무료 {i}위: {price}원")

        # 2. 유/무료 전체 섹션 수집
        all_items = soup.select("#lowPrice_r .diff_item") or soup.select(".diff_item")
        for i, item in enumerate(all_items[:5], 1):
            price = item.select_one(".prc_c").text.strip() if item.select_one(".prc_c") else "0"
            rows.append([now_str, "전체섹션", f"{i}위", price])
            print(f"전체 {i}위: {price}원")

        # 3. 구글 시트로 전송
        try:
            # 깃허브 Secret에 저장한 JSON 키를 불러옵니다
            creds_json = os.environ.get('GCP_CREDENTIALS')
            if not creds_json:
                raise Exception("GCP_CREDENTIALS Secret이 설정되지 않았습니다.")
            
            creds = json.loads(creds_json)
            gc = gspread.service_account_from_dict(creds)
            
            # 시트 열기 및 데이터 추가
            sh = gc.open_by_key(SH_ID)
            worksheet = sh.get_worksheet(0) # 첫 번째 탭 선택
            worksheet.append_rows(rows)
            print(f"\n✅ 성공: {len(rows)}개의 데이터를 시트에 기록했습니다.")
            
        except Exception as e:
            print(f"\n❌ 시트 저장 실패: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
