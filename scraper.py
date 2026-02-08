import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime

async def get_danawa_data():
    async with async_playwright() as p:
        # 브라우저 실행
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        url = "https://prod.danawa.com/info/?pcode=13412984"
        await page.goto(url, wait_until="networkidle")
        
        # [핵심] 화면을 아래로 천천히 내려서 가격표가 다 뜨게 만듭니다.
        for _ in range(3):
            await page.mouse.wheel(0, 1000)
            await asyncio.sleep(1)

        # 가격표가 나타날 때까지 대기
        try:
            await page.wait_for_selector(".diff_item", timeout=15000)
        except:
            print("데이터를 찾는 중 시간이 초과되었습니다. (차단 가능성 있음)")

        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n===== 수집 시간(KST): {now_str} =====")

        # ---------------------------------------------------------
        # 1. 무료배송 섹션 (왼쪽 바구니 탐색)
        # ---------------------------------------------------------
        print("\n[1] 무료배송 섹션 상위 5개")
        # 여러가지 가능성 있는 클래스를 모두 체크합니다.
        left_items = soup.select(".lowest_left .diff_item") or soup.select("#lowPrice_l .diff_item")
        
        if not left_items:
            print(" - 무료배송 정보를 찾을 수 없습니다.")
        else:
            for i, item in enumerate(left_items[:5], 1):
                mall = item.select_one(".shop_logo img")['alt'] if item.select_one(".shop_logo img") else "판매처미상"
                price = item.select_one(".prc_c").text.strip() if item.select_one(".prc_c") else "정보없음"
                print(f"{i}위: {mall} | {price}원")

        print("-" * 30)

        # ---------------------------------------------------------
        # 2. 유/무료 포함 전체 섹션 (오른쪽 바구니 탐색)
        # ---------------------------------------------------------
        print("[2] 유/무료 포함 전체 섹션 상위 5개")
        right_items = soup.select(".lowest_right .diff_item") or soup.select("#lowPrice_r .diff_item")
        
        if not right_items:
            # 좌우 분리가 안 된 페이지라면 전체 목록에서 가져옵니다.
            right_items = soup.select(".diff_item") 
            
        if not right_items:
            print(" - 전체 정보를 찾을 수 없습니다.")
        else:
            for i, item in enumerate(right_items[:5], 1):
                mall = item.select_one(".shop_logo img")['alt'] if item.select_one(".shop_logo img") else "판매처미상"
                price = item.select_one(".prc_c").text.strip() if item.select_one(".prc_c") else "정보없음"
                delivery = item.select_one(".delivery_base").text.strip() if item.select_one(".delivery_base") else "배송비 별도"
                print(f"{i}위: {mall} | {price}원 ({delivery})")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
