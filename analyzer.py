import asyncio
import random
import re
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright
import gspread

# --- 설정 ---
SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ"

# 테스트용 상품 (콘드1200)
PRODUCTS = {
    "콘드1200": [
        "https://prod.danawa.com/info/?pcode=13412984", "https://prod.danawa.com/info/?pcode=13413059",
        "https://prod.danawa.com/info/?pcode=13413086", "https://prod.danawa.com/info/?pcode=13413254",
        "https://prod.danawa.com/info/?pcode=13678937", "https://prod.danawa.com/info/?pcode=13413314"
    ]
}

async def get_mall_set_price(page, url, idx_name):
    try:
        print(f"🔎 {idx_name} 분석 시작: {url}")
        
        # 1. 다나와 페이지 접속
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # 2. 가격 비교 리스트 로딩 대기
        try:
            # 리스트 전체를 감싸는 영역이 나타날 때까지 대기
            await page.wait_for_selector("#productPriceComparison, .diff_item", timeout=20000)
            print("   ✅ 리스트 로드 확인")
        except:
            print("   ⚠️ 리스트 로딩 지연 중...")

        await asyncio.sleep(5)
        # 오른쪽 섹션 로딩을 위해 스크롤을 여러 번 나눠서 수행
        await page.evaluate("window.scrollTo(0, 500)")
        await asyncio.sleep(1)
        await page.evaluate("window.scrollTo(0, 1500)")
        await asyncio.sleep(4)

        # 3. Playwright 직접 접근 방식으로 유료배송 1위 찾기 (BS4보다 강력함)
        items = await page.query_selector_all(".diff_item, [id^='productItem']")
        
        target_link = None
        for item in items:
            inner_text = await item.inner_text()
            
            # 유료배송 판별: '무료'가 없고, '원'이나 '배송비'가 있는 경우
            if "무료" not in inner_text and ("원" in inner_text or "배송비" in inner_text):
                # 아이템 내의 모든 링크 추출 시도
                a_tags = await item.query_selector_all("a")
                for a in a_tags:
                    href = await a.get_attribute("href")
                    # 다나와 광고 링크(ad.danawa)나 상품 링크(v_gate) 등 유효한 주소 찾기
                    if href and ("danawa.com" in href or "v_gate" in href or href.startswith("http")):
                        if "javascript" in href: continue # 자바스크립트 함수 제외
                        
                        if href.startswith("//"): target_link = "https:" + href
                        elif href.startswith("/"): target_link = "https://prod.danawa.com" + href
                        else: target_link = href
                        break
                if target_link: break

        if not target_link:
            print(f"   ❌ {idx_name}: 유료배송 링크 추출 실패 (아이템 {len(items)}개 검사함)")
            return "업체미발견", 0

        # 4. 판매처 이동 (리다이렉션 고려)
        print(f"   🚀 판매처 이동 시작...")
        await page.goto(target_link, wait_until="load", timeout=90000)
        
        # 쇼핑몰 도착 후 충분히 대기 (경유 페이지가 길 수 있음)
        await asyncio.sleep(12) 
        
        # 팝업창이 뜨는 경우 닫기 (선택사항이나 안정성을 위해 추가)
        final_url = page.url
        print(f"   🔗 최종 도착: {final_url[:70]}...")

        mall_name = "기타몰"
        set_price = 0

        # 5. 가격 추출 (옥션/지마켓 정밀 타격)
        if "auction.co.kr" in final_url or "gmarket.co.kr" in final_url:
            mall_name = "옥션" if "auction" in final_url else "지마켓"
            # 옥션/지마켓의 다양한 가격 태그 후보군
            price_selectors = [
                "#lblSellingPrice",    # 옥션/지마켓 기본 판매가
                ".price_real",         # 지마켓 구버전
                ".price_main",         # 지마켓 신버전
                "span.price",          # 일반
                ".un-tr-price"         # 특수 케이스
            ]
            for s in price_selectors:
                try:
                    el = await page.query_selector(s)
                    if el:
                        txt = await el.inner_text()
                        num = re.sub(r'[^0-9]', '', txt)
                        if num:
                            set_price = int(num)
                            break
                except: continue
        
        return mall_name, set_price

    except Exception as e:
        print(f"   ⚠️ 에러 상세: {str(e)[:100]}")
        return "에러", 0

async def main():
    # 구글 시트 인증
    try:
        creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
        creds = json.loads(creds_raw)
        gc = gspread.service_account_from_dict(creds)
        sh = gc.open_by_key(SH_ID)
    except Exception as e:
        print(f"❌ 구글 시트 연결 실패: {e}")
        return

    # 탭 확인 및 생성
    try:
        wks = sh.worksheet("정산가분석")
    except:
        wks = sh.add_worksheet(title="정산가분석", rows="1000", cols="6")
        wks.append_row(["수집시간", "상품명", "구성", "판매처", "설정가", "정산금(85%)"])

    async with async_playwright() as p:
        # 브라우저 실행 (서버 환경에 최적화)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for prod_name, urls in PRODUCTS.items():
            print(f"\n--- {prod_name} 수집 시작 ---")
            for idx, url in enumerate(urls):
                if not url or url.strip() == "": continue
                
                mall, price = await get_mall_set_price(page, url, f"{idx+1}개입")
                
                if price > 0:
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    settle = int(price * 0.85)
                    wks.append_row([now_str, prod_name, f"{idx+1}개입", mall, price, settle])
                    print(f"   ✅ 성공: {mall} / {price}원 (정산가: {settle}원)")
                else:
                    print(f"   ❌ 수집실패 (결과값 없음)")
                
                # 차단 방지를 위한 랜덤 휴식
                await asyncio.sleep(random.randint(8, 15))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
