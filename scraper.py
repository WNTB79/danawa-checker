import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import datetime

async def get_danawa_data():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        url = "https://prod.danawa.com/info/?pcode=13412984"
        await page.goto(url, wait_until="networkidle")
        
        # 가격표가 나타날 때까지 대기
        await page.wait_for_selector(".diff_item", timeout=10000)
        
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        
        print(f"\n===== 수집 시간: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====")

        # 1. 무료배송 섹션 (보통 왼쪽: lowest_left)
        print("\n[1] 무료배송 섹션 상위 5개")
        free_items = soup.select(".lowest_left .diff_item")
        for i, item in enumerate(free_items[:5], 1):
            mall = item.select_one(".shop_logo img")['alt'] if item.select_one(".shop_logo img") else "판매처미상"
            price = item.select_one(".prc_c").text.strip() if item.select_one(".prc_c") else "가격없음"
            print(f"{i}위: {mall} | {price}원")

        print("-" * 30)

        # 2. 유/무료 포함 전체 섹션 (보통 오른쪽: lowest_right)
        print("[2] 유/무료 포함 전체 섹션 상위 5개")
        all_items = soup.select(".lowest_right .diff_item")
        for i, item in enumerate(all_items[:5], 1):
            mall = item.select_one(".shop_logo img")['alt'] if item.select_one(".shop_logo img") else "판매처미상"
            price = item.select_one(".prc_c").text.strip() if item.select_one(".prc_c") else "가격없음"
            # 배송비 정보가 따로 있다면 가져오기
            delivery = item.select_one(".delivery_base").text.strip() if item.select_one(".delivery_base") else ""
            print(f"{i}위: {mall} | {price}원 ({delivery})")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
