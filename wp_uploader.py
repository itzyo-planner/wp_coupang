"""
워드프레스 REST API 업로드 모듈
"""
import requests
import base64
import os
from dotenv import load_dotenv

load_dotenv()

WP_URL = os.getenv("WP_URL", "").rstrip("/")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")
POST_STATUS = os.getenv("POST_STATUS", "publish")
POST_CATEGORY_ID = int(os.getenv("POST_CATEGORY_ID", 1))


def _auth_header():
    credentials = f"{WP_USERNAME}:{WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode()).decode("utf-8")
    return {"Authorization": f"Basic {token}"}


def upload_image_from_url(image_url: str, filename: str) -> int | None:
    """
    외부 이미지 URL을 워드프레스 미디어 라이브러리에 업로드
    Returns: 업로드된 미디어 ID
    """
    try:
        img_response = requests.get(image_url, timeout=10)
        img_response.raise_for_status()

        headers = {
            **_auth_header(),
            "Content-Disposition": f'attachment; filename="{filename}.jpg"',
            "Content-Type": "image/jpeg",
        }

        response = requests.post(
            f"{WP_URL}/wp-json/wp/v2/media",
            headers=headers,
            data=img_response.content,
            timeout=30
        )
        response.raise_for_status()
        return response.json().get("id")

    except Exception as e:
        print(f"[이미지 업로드 실패] {e}")
        return None


def build_post_content(product: dict) -> str:
    """상품 정보로 HTML 포스트 본문 생성"""
    price = f"{int(product['productPrice']):,}" if product.get("productPrice") else "가격 미정"
    rating = product.get("rating", "N/A")
    review_count = product.get("reviewCount", 0)
    coupang_url = product.get("coupangUrl", "#")
    image_url = product.get("productImage", "")

    content = f"""
<div class="coupang-product">
  <div class="product-image" style="text-align:center; margin-bottom:20px;">
    <img src="{image_url}" alt="{product['productName']}" style="max-width:400px; border-radius:8px;" />
  </div>

  <div class="product-info">
    <h2 style="font-size:1.4em; margin-bottom:10px;">{product['productName']}</h2>

    <table style="width:100%; border-collapse:collapse; margin-bottom:20px;">
      <tr>
        <td style="padding:8px; background:#f5f5f5; font-weight:bold; width:30%;">판매가</td>
        <td style="padding:8px;">&#8361; {price}</td>
      </tr>
      <tr>
        <td style="padding:8px; background:#f5f5f5; font-weight:bold;">평점</td>
        <td style="padding:8px;">{'⭐' * int(float(rating))} ({rating}) — 리뷰 {review_count:,}개</td>
      </tr>
    </table>

    <div style="text-align:center; margin:30px 0;">
      <a href="{coupang_url}" target="_blank" rel="noopener sponsored"
         style="background:#e74c3c; color:#fff; padding:15px 40px; text-decoration:none;
                border-radius:5px; font-size:1.1em; font-weight:bold; display:inline-block;">
        🛒 쿠팡에서 최저가 보기
      </a>
    </div>
  </div>
</div>

<hr style="margin:30px 0;" />
<p style="font-size:0.85em; color:#888;">
  이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.
</p>
"""
    return content


def post_to_wordpress(product: dict) -> dict | None:
    """
    워드프레스에 상품 포스트 업로드
    Returns: 생성된 포스트 정보
    """
    title = f"[쿠팡 추천] {product['productName']}"
    content = build_post_content(product)

    # 이미지 업로드
    featured_media_id = None
    if product.get("productImage"):
        safe_name = f"product_{product.get('productId', 'img')}"
        featured_media_id = upload_image_from_url(product["productImage"], safe_name)

    payload = {
        "title": title,
        "content": content,
        "status": POST_STATUS,
        "categories": [POST_CATEGORY_ID],
        "tags": [],
    }

    if featured_media_id:
        payload["featured_media"] = featured_media_id

    headers = {
        **_auth_header(),
        "Content-Type": "application/json"
    }

    response = requests.post(
        f"{WP_URL}/wp-json/wp/v2/posts",
        json=payload,
        headers=headers,
        timeout=30
    )
    response.raise_for_status()
    result = response.json()

    print(f"[업로드 성공] {title} → {result.get('link')}")
    return result


def get_existing_post_titles() -> set:
    """이미 업로드된 포스트 제목 목록 (중복 방지)"""
    titles = set()
    page = 1
    while True:
        response = requests.get(
            f"{WP_URL}/wp-json/wp/v2/posts",
            params={"per_page": 100, "page": page, "categories": POST_CATEGORY_ID},
            headers=_auth_header(),
            timeout=15
        )
        if response.status_code != 200:
            break
        posts = response.json()
        if not posts:
            break
        for post in posts:
            titles.add(post.get("title", {}).get("rendered", ""))
        page += 1
    return titles
