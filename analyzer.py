import asyncio
import re
import json
import os
import random
from datetime import datetime
from playwright.async_api import async_playwright
import gspread

# --- 설정 ---
SH_ID = "1hKx0tg2jkaVswVIfkv8jbqx0QrlRkftFtjtVlR09cLQ"
# 상품 코드만 리스트로 관리 (상세페이지 접근용)
PCODES = {
    "1개입": "13412984", "2개입": "13413059", "3개입": "13413086",
    "4개입": "13413254", "5개입": "13678937", "6개입": "13413314"
}

async def get_price_final(browser_context, pcode, idx_name):
    page = await browser_context.new_page()
    try:
        print(f"🔎 {idx_name} 분석 중 (코드: {pcode})")
        
        # 다나와 상세페이지 접속
        url = f"https://prod.danawa.com/info/?pcode={pcode}"
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(7) 

        # [전략] 화면에 안 보이면 HTML 소스 전체에서 쇼핑몰 이동 링크를 정규식으로 추출
        content = await page.content()
        
        # 다나와 로딩 브릿지 주소 패턴 추출 (loadingBridge 문자열 포함된 모든 URL)
        bridge_links = re.findall(r'https?://[^\s"\']+loadingBridge[^\s"\']+', content)
        
        target_link = None
        # blogNum=9(지마켓), blogNum=7(옥션), blogNum=15(11번가) 우선 탐색
        for link in bridge_links:
            if any(key in link for key in ["blogNum=9", "blogNum=7", "blogNum=15"]):
                target_link = link
                break
        
        if not target_link and bridge_links:
            target_link = bridge_links[0]

        if not target_link:
            print("   ❌ HTML 소스에서 판매처 링크를 찾지 못했습니다.")
            return None, 0

        # 쇼핑몰 상세페이지로 새 창 열기
        mall_page = await browser_context.new_page()
        print(f"   🚀 쇼핑몰 강제 이동 중...")
        await mall_page.goto(target_link, wait_until="load", timeout=90000)
        await asyncio.sleep(12)

        # 지마켓/옥션 리스트로 튕겼을 때 상품번호로 상세페이지 재조합
        if "search" in mall_page.url or "keyword=" in mall_page.url:
            item_no = re.search(r'(itemno|goodscode|goodsNo)=(\d+)', target_link)
            if item_no:
                num = item_no.group(2)
                # 지마켓(blogNum=9)이면 지마켓 상세페이지로, 아니면 옥션 상세페이지로 강제 이동
                d_url = f"https://item.gmarket.co.kr/Item?goodscode={num}" if "blogNum=9" in target_link else f"https://itempage3.auction.co.kr/DetailView.aspx?itemno={num}"
                await mall_page.goto(d_url, wait_until="load")
                await asyncio.sleep(8)

        print(f"   🔗 최종 도착: {mall_page.url[:60]}")
        mall_name = "지마켓" if "gmarket" in mall_page.url else "옥션" if "auction" in mall_page.url else "11번가" if "11st" in mall_page.url else "기타"
        
        # 최종 가격 추출 (패턴 매칭 강화)
        price = 0
        mall_content = await mall_page.content()
        matches = re.findall(r'([0-9,]{4,})\s*원', mall_content)
        for m in matches:
            num = int(re.sub(r'[^0-9]', '', m))
            if 10000 < num < 1000000:
                price = num
                break

        await mall_page.close()
        return mall_name, price

    except Exception as e:
        print(f"   ⚠️ 오류: {str(e)[:50]}")
        return None, 0
    finally:
        await page.close()

async def main():
    # Google 시트 인증
    creds_raw = os.environ.get('GCP_CREDENTIALS', '').strip()
    creds = json.loads(creds_raw)
    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_key(SH_ID)
    wks = sh.worksheet("정산가분석")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        print(f"--- 콘드1200 최종 정밀 수집 시작 ---")
        for idx_name, pcode in PCODES.items():
            mall, price = await get_price_final(context, pcode, idx_name)
            if price > 0:
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                # 시트에 [날짜, 제품명, 개입, 몰이름, 원가, 정산가(85%)] 기록
                wks.append_row([now, "콘드1200", idx_name, mall, price, int(price * 0.85)])
                print(f"   ✅ 시트 기록 성공: {price}원")
            else:
                print("   ❌ 수집 실패")
            
            # 차단 방지를 위해 랜덤하게 쉬기
            await asyncio.sleep(random.randint(15, 25))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
