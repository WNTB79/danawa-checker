import asyncio
import random
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import gspread
import json
import os

SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ" 

async def get_danawa_data():
    # 1. 랜덤 대기
    wait_sec = random.randint(0, 1200)
    print(f"🕒 차단 방지를 위해 {wait_sec // 60}분 {wait_sec % 60}초 대기...")
    await asyncio.sleep(wait_sec)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        final_matrix = [[now_str, f"{i}위"] for i in range(1, 6)]
        temp_prices = [[] for _ in range(5)]

        urls = [
            "https://prod.danawa.com/info/?pcode=13412984",
            "https://prod.danawa.com/info/?pcode=13413059",
            "https://prod.danawa.com/info/?pcode=13413086",
            "https://prod.danawa.com/info/?pcode=13413254",
            "https://prod.danawa.com/info/?pcode=13678937",
            "https://prod.danawa.com/info/?pcode=13413314"
        ]

        for idx, url in enumerate(urls):
            try:
                print(f"🚀 {idx+1}개 분석 중...")
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(8)
                await page.evaluate("window.scrollTo(0, 1500)")
                await asyncio.sleep(4)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                items = soup.select(".diff_item, .product-item, li[id^='productItem']")
                
                right_items = []
                for item in items:
                    all_text = item.get_text(separator=' ', strip=True)
                    if "무료배송" not in all_text and ("배송비" in all_text or "원" in all_text):
                        price_tag = item.select_one(".prc_c, .price")
                        if price_tag:
                            right_items.append(item)

                for i in range(5):
                    if i < len(right_items):
                        p_tag = right_items[i].select_one(".prc_c, .price")
                        price = "".join(filter(str.isdigit, p_tag.get_text()))
                        temp_prices[i].append(int(price) if price else 0)
                    else:
                        temp_prices[i].append(0)
            except Exception as e:
                print(f"⚠️ 에러: {e}")
                for i in range(5): temp_prices[i].append(0)

        # --- 변동 계산 및 전체 감시 로직 ---
        try:
            creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
            creds = json.loads(creds_raw)
            gc = gspread.service_account_from_dict(creds)
            sh = gc.open_by_key(SH_ID)
            wks = sh.get_worksheet(0)

            # 1. 시트의 이전 데이터(2행~6행) 5줄을 한꺼번에 가져옵니다.
            # 가격 데이터만 뽑아서 비교하기 위해 C, E, G, I, K, M열만 필터링합니다.
            last_rows_data = wks.get_all_values()[1:6] # 제목 제외 5줄
            
            prev_all_prices = []
            for row in last_rows_data:
                row_prices = []
                for pi in [2, 4, 6, 8, 10, 12]: # C, E, G, I, K, M열
                    val = row[pi].replace(",", "") if len(row) > pi else "0"
                    row_prices.append(int(val) if val.isdigit() else 0)
                prev_all_prices.append(row_prices)

            # 2. 현재 수집한 temp_prices와 이전 prev_all_prices를 비교합니다.
            is_changed = temp_prices != prev_all_prices

            if is_changed:
                # 데이터 재구성 및 기호 적용
                for i in range(5):
                    for col_idx in range(6):
                        curr_p = temp_prices[i][col_idx]
                        prev_p = prev_all_prices[i][col_idx]
                        
                        diff = curr_p - prev_p
                        if diff > 0:
                            diff_val = f"▲{abs(diff):,}"
                        elif diff < 0:
                            diff_val = f"▼{abs(diff):,}"
                        else:
                            diff_val = "-"
                        
                        final_matrix[i].extend([curr_p, diff_val])
                
                wks.insert_rows(final_matrix, row=2)
                print(f"✅ 전체 데이터 중 변동 감지! 시트에 기록했습니다.")
            else:
                print(f"⏭️ 모든 순위/구성의 가격이 동일함. 기록 건너뜀.")

        except Exception as e:
            print(f"❌ 오류: {e}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
