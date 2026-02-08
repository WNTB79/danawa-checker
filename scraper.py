import requests
from bs4 import BeautifulSoup
import datetime

def get_danawa_data():
    url = "https://prod.danawa.com/info/?pcode=13412984" # 판매자님이 주신 링크
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"}
    
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 가격 비교 목록 추출
    items = soup.select(".diff_item")[:5]
    print(f"--- {datetime.datetime.now()} 기준 최저가 순위 ---")
    
    for i, item in enumerate(items, 1):
        mall = item.select_one(".shop_logo img")['alt'] if item.select_one(".shop_logo img") else "판매처미상"
        price = item.select_one(".prc_c").text.strip()
        print(f"{i}위: {mall} / {price}원")

if __name__ == "__main__":
    get_danawa_data()
