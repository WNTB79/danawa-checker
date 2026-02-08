import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime

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
        
        # 1. 가격 비교 영역이 로드될 때까지 대기
        await asyncio.sleep(5)
        
        # 2. 무료배송 탭이 별도로 있다면 클릭 시도 (다나와 구조 대응)
        try:
            # '무료배송' 글자가 포함된 버튼이나 탭을 찾아 클릭 시뮬레이션
            free_ship_tab = page.locator("text='무료배송'").first
            if await free_ship_tab.is_visible():
                await free_ship_tab.click()
                await asyncio.sleep(2)
        except:
            pass

        # 3. 화면 스크롤 (데이터 활성화)
        await page.mouse.wheel(0, 1000)
        await asyncio.sleep(3)

        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n===== 수집 시간(KST): {now_str} =====")

        # ---------------------------------------------------------
        # [1] 무료배송 섹션 추출
        # ---------------------------------------------------------
        print("\n[1] 무료배송 섹션 상위 5개")
        # 왼쪽 섹션(#lowPrice_l) 또는 전체 리스트 중 배송비가 0원/무료인 항목 탐색
        free_items = soup.select("#lowPrice_l .diff_item") or soup.select(".lowest_left .diff_item")
        
        if not free_items:
            # 만약 섹션 분리가 안 되어 있다면 전체 리스트에서 '무료배송' 텍스트가 있는 것만 필터링
            all_items = soup.select(".diff_item")
            free_items = [item for item in all_items if "무료배송" in item.get_text()]

        if not free_items:
            print(" - 무료배송 정보를 찾을 수 없습니다.")
        else:
            for i, item in enumerate(free_items[:5], 1):
                price = item.select_one(".prc_c").text.strip() if item.select_one(".prc_c") else "정보없음"
                print(f"{i}위: {price}원 (무료배송)")

        print("-" * 30)

        # ---------------------------------------------------------
        # [2] 유/무료 포함 전체 섹션 추출
        # ---------------------------------------------------------
        print("[2] 유/무료 포함 전체 섹션 상위 5개")
        right_items = soup.select("#lowPrice_r .diff_item") or soup.select(".lowest_right .diff_item") or soup.select(".diff_item")

        for i, item in enumerate(right_items[:5], 1):
            price = item.select_one(".prc_c").text.strip() if item.select_one(".prc_c") else "정보없음"
            delivery = item.select_one(".delivery_base").text.strip() if item.select_one(".delivery_base") else "배송비 확인필요"
            print(f"{i}위: {price}원 ({delivery})")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
