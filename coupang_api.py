"""
쿠팡 파트너스 API 모듈
"""
import hmac
import hashlib
import urllib.parse
import datetime
import requests
import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_KEY = os.getenv("COUPANG_ACCESS_KEY")
SECRET_KEY = os.getenv("COUPANG_SECRET_KEY")
AFFILIATE_ID = os.getenv("COUPANG_AFFILIATE_ID")

DOMAIN = "https://api-gateway.coupang.com"


def _generate_hmac(method, url, secret_key, access_key):
    """쿠팡 API HMAC 서명 생성"""
    dt = datetime.datetime.utcnow()
    datetime_str = dt.strftime("%y%m%d")
    time_str = dt.strftime("%H%M%S")

    path, *query = url.split("?")
    query_string = query[0] if query else ""

    message = datetime_str + time_str + method + path + query_string

    signature = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_str}{time_str}, signature={signature}"


def get_best_products(keyword: str, limit: int = 10) -> list:
    """
    키워드로 쿠팡 상품 검색
    Returns: 상품 리스트 [{"productId", "productName", "productPrice", "productImage", "productUrl"}]
    """
    path = "/v2/providers/affiliate_open_api/apis/openapi/products/search"
    query = f"keyword={urllib.parse.quote(keyword)}&limit={limit}"
    url = f"{path}?{query}"

    authorization = _generate_hmac("GET", url, SECRET_KEY, ACCESS_KEY)

    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json"
    }

    response = requests.get(DOMAIN + url, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()

    products = []
    for item in data.get("data", {}).get("productData", []):
        products.append({
            "productId": item.get("productId"),
            "productName": item.get("productName"),
            "productPrice": item.get("productPrice"),
            "productImage": item.get("productImage"),
            "productUrl": item.get("productUrl"),
            "coupangUrl": item.get("shortenUrl") or item.get("landingUrl"),
            "rating": item.get("productRating"),
            "reviewCount": item.get("reviewCount"),
        })

    return products


def get_trending_products(category_id: str = None, limit: int = 10) -> list:
    """
    베스트셀러 / 트렌딩 상품 가져오기
    """
    path = "/v2/providers/affiliate_open_api/apis/openapi/products/bestcategories"
    query = f"categoryId={category_id}&limit={limit}" if category_id else f"limit={limit}"
    url = f"{path}?{query}"

    authorization = _generate_hmac("GET", url, SECRET_KEY, ACCESS_KEY)

    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json"
    }

    response = requests.get(DOMAIN + url, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()

    products = []
    for item in data.get("data", []):
        products.append({
            "productId": item.get("productId"),
            "productName": item.get("productName"),
            "productPrice": item.get("productPrice"),
            "productImage": item.get("productImage"),
            "coupangUrl": item.get("shortenUrl") or item.get("landingUrl"),
            "rating": item.get("productRating"),
            "reviewCount": item.get("reviewCount"),
        })

    return products
