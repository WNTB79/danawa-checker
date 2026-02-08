import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime

async def get_danawa_data():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 실제 사람의 브라우저 정보를 더 상세히 흉내냅니다.
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        url = "https://prod.danawa.com/info/?pcode=13412984"
        await page.goto(url, wait_until="networkidle")
        
        # 가격표 영역이 로딩될 때까지 최대 15초 대기
        try:
            await page.wait_for_selector(".diff_item", timeout=15000)
            # 데이터를 확실히 불러오기 위해 화면을 아래로 살짝 내립니다.
            await page.mouse.wheel(0, 500)
            await asyncio.sleep(2) 
        except:
            print("대기 시간 초과: 가격 리스트를 찾지 못했습니다.")

        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n===== 수집 시간(KST): {now_str} =====")

        # 섹션별 데이터 수집
        # 1. 왼쪽 (무료배송 섹션)
        print("\n[1] 무료배송 섹션 상위 5개")
        left_section = soup.select("#lowPrice_l .diff_item") # ID로 직접 접근
        if not left_section: # 클래스로 재시도
            left_section = soup.select(".lowest_left .diff_item")
            
        for i, item in enumerate(left_section[:5], 1):
            mall = item.select_one(".shop_logo img")['alt'] if item.select_one(".shop_logo img") else "판매처미상"
            price = item.select_one(".prc_c").text.strip() if item.select_one(".prc_c") else "정보없음"
            print(f"{i}위: {mall} | {price}원")

        print("-" * 30)

        # 2. 오른쪽 (전체 섹션)
        print("[2] 유/무료 포함 전체 섹션 상위 5개")
        right_section = soup.select("#lowPrice_r .diff_item") # ID로 직접 접근
        if not right_section: # 클래스로 재시도
            right_section = soup.select(".lowest_right .diff_item")
            
        for i, item in enumerate(right_section[:5], 1):
            mall = item.select_one(".shop_logo img")['alt'] if item.select_one(".shop_logo img") else "판매처미상"
            price = item.select_one(".prc_c").text.strip() if item.select_one(".prc_c") else "정보없음"
            delivery = item.select_one(".delivery_base").text.strip() if item.select_one(".delivery_base") else "배송비 별도"
            print(f"{i}위: {mall} | {price}원 ({delivery})")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
