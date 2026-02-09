import asyncio
import random
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import gspread
import json
import os

# [수정포인트 1] 시트 ID와 탭 이름을 본인 것으로 확인하세요!
SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ" 
TAB_NAME = "콘드1200" # 시트 하단 탭 이름을 여기에 정확히 적어주세요.

async def get_danawa_data():
    # 랜덤 대기 (테스트 시에는 숫자를 줄여서 사용하세요)
    wait_sec = random.randint(0, 600)
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
            
            # [수정포인트 2] 지정한 탭 이름을 사용합니다.
            wks = sh.worksheet(TAB_NAME)

            # 시트 상단 P1 셀에 마지막 체크 시각을 무조건 기록합니다.
            wks.update_acell('P1', f"마지막 체크: {now_str}")

            # 시트의 이전 데이터(2행~6행) 5줄을 한꺼번에 가져옵니다.
            rows = wks.get_all_values()
            last_rows_data = rows[1:6] if len(rows) >= 6 else []
            
            prev_all_prices = []
            # 이전 가격 인덱스 (C, E, G, I, K, M열 -> 2, 4, 6, 8, 10, 12)
            for row in last_rows_data:
                row_prices = []
                for pi in [2, 4, 6, 8, 10, 12]:
                    val = row[pi].replace(",", "") if len(row) > pi else "0"
                    row_prices.append(int(val) if val.isdigit() else 0)
                prev_all_prices.append(row_prices)

            # 데이터가 아예 없는 초기 상태 대비 로직
            if not prev_all_prices:
                prev_all_prices = [[0]*6 for _ in range(5)]

            # 현재 수집한 temp_prices와 이전 prev_all_prices를 비교
            is_changed = (temp_prices != prev_all_prices)

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
                print(f"✅ 변동 감지! 시트에 기록 완료 및 체크 시각 업데이트.")
            else:
                print(f"⏭️ 가격 동일. 기록은 건너뛰고 P1 셀의 체크 시각만 업데이트함.")

        except Exception as e:
            print(f"❌ 오류 발생: {e}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
