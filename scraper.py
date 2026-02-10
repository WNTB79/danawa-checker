import asyncio
import random
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime
import gspread
import json
import os

SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ" 

# [상품 리스트 정의] 탭이름: [1개, 2개, 3개, 4개, 5개, 6개 주소]
PRODUCTS = {
    "콘드1200": [
        "https://prod.danawa.com/info/?pcode=13412984", "https://prod.danawa.com/info/?pcode=13413059",
        "https://prod.danawa.com/info/?pcode=13413086", "https://prod.danawa.com/info/?pcode=13413254",
        "https://prod.danawa.com/info/?pcode=13678937", "https://prod.danawa.com/info/?pcode=13413314"
    ],
    "MBP": [
        "https://prod.danawa.com/info/?pcode=11901550", "https://prod.danawa.com/info/?pcode=11901592",
        "https://prod.danawa.com/info/?pcode=11901679", "https://prod.danawa.com/info/?pcode=11901682",
        "https://prod.danawa.com/info/?pcode=12005351", "https://prod.danawa.com/info/?pcode=11901862"
    ],
    "덴마크유산균": [
        "https://prod.danawa.com/info/?pcode=4087011", "https://prod.danawa.com/info/?pcode=4491609",
        "https://prod.danawa.com/info/?pcode=4491621", "https://prod.danawa.com/info/?pcode=4491644",
        "https://prod.danawa.com/info/?pcode=14863700", "https://prod.danawa.com/info/?pcode=4491661"
    ],
    "난각막": [
        "https://prod.danawa.com/info/?pcode=67605707", "https://prod.danawa.com/info/?pcode=67605761",
        "https://prod.danawa.com/info/?pcode=67605812", "https://prod.danawa.com/info/?pcode=67605743",
        "https://prod.danawa.com/info/?pcode=67605716", "https://prod.danawa.com/info/?pcode=67605794"
    ],
    "폴리5": [
        "https://prod.danawa.com/info/?pcode=3742572", "https://prod.danawa.com/info/?pcode=3966366",
        "https://prod.danawa.com/info/?pcode=3966388", "https://prod.danawa.com/info/?pcode=8373021",
        "https://prod.danawa.com/info/?pcode=11003949", "https://prod.danawa.com/info/?pcode=5711776"
    ],
    "폴리20": [
        "https://prod.danawa.com/info/?pcode=13249364", "https://prod.danawa.com/info/?pcode=13249382",
        "https://prod.danawa.com/info/?pcode=13249388", "https://prod.danawa.com/info/?pcode=13249391",
        "https://prod.danawa.com/info/?pcode=13249409", "https://prod.danawa.com/info/?pcode=13249415"
    ],
    "파비플로라": [
        "https://prod.danawa.com/info/?pcode=72980105", "https://prod.danawa.com/info/?pcode=73069886",
        "https://prod.danawa.com/info/?pcode=73069745", "https://prod.danawa.com/info/?pcode=73069754",
        "https://prod.danawa.com/info/?pcode=73069682", "https://prod.danawa.com/info/?pcode=73069688"
    ],
    "알부민": [
        "https://prod.danawa.com/info/?pcode=94451009", "https://prod.danawa.com/info/?pcode=94451012",
        "https://prod.danawa.com/info/?pcode=94633247", "https://prod.danawa.com/info/?pcode=95053424",
        "https://prod.danawa.com/info/?pcode=95053427", "https://prod.danawa.com/info/?pcode=95053430"
    ],
    "마일드센스": [
        "https://prod.danawa.com/info/?pcode=5490866", "https://prod.danawa.com/info/?pcode=5490869",
        "https://prod.danawa.com/info/?pcode=6176420", "https://prod.danawa.com/info/?pcode=5940121",
        "https://prod.danawa.com/info/?pcode=12257999", "https://prod.danawa.com/info/?pcode=5494129"
    ]
}

async def collect_product_data(page, urls):
    """한 상품(6개 주소)에 대한 데이터를 수집하는 함수"""
    matrix = [[datetime.now().strftime('%Y-%m-%d %H:%M:%S'), f"{i}위"] for i in range(1, 6)]
    temp_prices = [[] for _ in range(5)]

    for idx, url in enumerate(urls):
        try:
            print(f"   - {idx+1}개입 페이지 분석 중...")
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
                    if item.select_one(".prc_c, .price"):
                        right_items.append(item)

            for i in range(5):
                if i < len(right_items):
                    p_tag = right_items[i].select_one(".prc_c, .price")
                    price = "".join(filter(str.isdigit, p_tag.get_text()))
                    temp_prices[i].append(int(price) if price else 0)
                else:
                    temp_prices[i].append(0)
        except Exception as e:
            print(f"   ⚠️ 에러: {e}")
            for i in range(5): temp_prices[i].append(0)
    
    return matrix, temp_prices

async def main():
    # 1. 초기 지연 (0~10분)
    start_wait = random.randint(0, 600)
    print(f"🕒 첫 시작 전 {start_wait // 60}분 대기...")
    await asyncio.sleep(start_wait)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
        creds = json.loads(creds_raw)
        gc = gspread.service_account_from_dict(creds)
        sh = gc.open_by_key(SH_ID)

        # 등록된 모든 상품을 하나씩 수집
        for tab_name, urls in PRODUCTS.items():
            print(f"🚀 [{tab_name}] 수집 시작...")
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 수집 실행
            final_matrix, temp_prices = await collect_product_data(page, urls)
            
            try:
                wks = sh.worksheet(tab_name)
                wks.update_acell('P1', f"마지막 체크: {now_str}")
                
                rows = wks.get_all_values()
                last_rows_data = rows[1:6] if len(rows) >= 6 else []
                
                prev_all_prices = []
                for row in last_rows_data:
                    row_prices = []
                    for pi in [2, 4, 6, 8, 10, 12]:
                        val = row[pi].replace(",", "") if len(row) > pi else "0"
                        row_prices.append(int(val) if val.isdigit() else 0)
                    prev_all_prices.append(row_prices)

                if not prev_all_prices: prev_all_prices = [[0]*6 for _ in range(5)]

                if temp_prices != prev_all_prices:
                    for i in range(5):
                        for col_idx in range(6):
                            curr_p = temp_prices[i][col_idx]
                            prev_p = prev_all_prices[i][col_idx]
                            diff = curr_p - prev_p
                            diff_val = f"▲{abs(diff):,}" if diff > 0 else (f"▼{abs(diff):,}" if diff < 0 else "-")
                            final_matrix[i].extend([curr_p, diff_val])
                    
                    wks.insert_rows(final_matrix, row=2)
                    print(f"   ✅ {tab_name} 변동 감지 및 기록 완료.")
                else:
                    print(f"   ⏭️ {tab_name} 가격 동일. 건너뜀.")

            except Exception as e:
                print(f"   ❌ {tab_name} 시트 작업 오류: {e}")

            # --- [수정된 부분] 상품 간 휴식 시간 (1~3분 랜덤) ---
            if tab_name != list(PRODUCTS.keys())[-1]:
                # 300~600초에서 60~180초로 변경
                gap_wait = random.randint(60, 180) 
                print(f"💤 다음 상품 수집 전 {gap_wait // 60}분 {gap_wait % 60}초간 휴식합니다...")
                await asyncio.sleep(gap_wait)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
