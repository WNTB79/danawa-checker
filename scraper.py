import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import datetime

async def get_danawa_data():
    async with async_playwright() as p:
        # 브라우저 실행 (사람처럼 보이기 위해 옵션 추가)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # 상품 페이지 접속
        url = "https://prod.danawa.com/info/?pcode=13412984"
        await page.goto(url, wait_until="networkidle")
        
        # 가격 리스트가 화면에 나타날 때까지 최대 10초 대기
        await page.wait_for_selector(".diff_item", timeout=10000)
        
        # 페이지 전체 내용을 가져와서 분석
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        items = soup.select(".diff_item")
        
        print(f"--- {datetime.datetime.now()} 기준 수집 결과 ---")
        
        count = 0
        for item in items:
            if count >= 5: break # 상위 5개만
            
            # 업체명 (이미지 alt 태그나 텍스트 추출)
            mall_img = item.select_one(".shop_logo img")
            mall_name = mall_img['alt'] if mall_img and mall_img.has_attr('alt') else "판매처미상"
            
            # 가격
            price_element = item.select_one(".prc_c")
            if price_element:
                price = price_element.text.strip()
                print(f"{count+1}위: {mall_name} | 가격: {price}원")
                count += 1
        
        if count == 0:
            print("데이터를 찾지 못했습니다. 사이트 구조를 다시 확인해야 합니다.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_danawa_data())
