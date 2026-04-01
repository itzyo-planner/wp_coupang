"""
워드프레스 × 쿠팡 파트너스 자동 업로드 메인
"""
import os
import time
import schedule
import argparse
from dotenv import load_dotenv

from coupang_api import get_best_products, get_trending_products
from wp_uploader import post_to_wordpress, get_existing_post_titles

load_dotenv()

POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", 5))
SCHEDULE_HOURS = int(os.getenv("SCHEDULE_INTERVAL_HOURS", 6))

# 업로드할 키워드 목록 (원하는 키워드 추가)
KEYWORDS = [
    "노트북",
    "무선이어폰",
    "공기청정기",
    "전기밥솥",
    "스마트워치",
    "가습기",
    "블루투스스피커",
    "로봇청소기",
]


def run_upload():
    """키워드 기반 상품 검색 후 워드프레스에 업로드"""
    print("\n" + "=" * 50)
    print("🚀 쿠팡 파트너스 자동 업로드 시작")
    print("=" * 50)

    # 기존 포스트 제목 수집 (중복 방지)
    print("📋 기존 포스트 확인 중...")
    existing_titles = get_existing_post_titles()
    print(f"  → 기존 포스트 {len(existing_titles)}개 확인 완료")

    uploaded = 0
    keyword_index = 0

    while uploaded < POSTS_PER_RUN and keyword_index < len(KEYWORDS):
        keyword = KEYWORDS[keyword_index]
        keyword_index += 1

        print(f"\n🔍 키워드 검색: '{keyword}'")
        try:
            products = get_best_products(keyword, limit=5)
        except Exception as e:
            print(f"  → API 오류: {e}")
            continue

        for product in products:
            if uploaded >= POSTS_PER_RUN:
                break

            title_check = f"[쿠팡 추천] {product['productName']}"
            if title_check in existing_titles:
                print(f"  → 이미 업로드됨, 스킵: {product['productName'][:30]}...")
                continue

            try:
                post_to_wordpress(product)
                existing_titles.add(title_check)
                uploaded += 1
                time.sleep(2)  # API 부하 방지
            except Exception as e:
                print(f"  → 업로드 실패: {e}")

    print(f"\n✅ 완료: {uploaded}개 포스트 업로드")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="쿠팡 파트너스 × 워드프레스 자동 업로드")
    parser.add_argument("--run-once", action="store_true", help="한 번만 실행")
    parser.add_argument("--keyword", type=str, help="특정 키워드로 바로 실행")
    args = parser.parse_args()

    if args.keyword:
        # 특정 키워드로 즉시 실행
        from coupang_api import get_best_products
        products = get_best_products(args.keyword, limit=POSTS_PER_RUN)
        existing = get_existing_post_titles()
        for product in products:
            title_check = f"[쿠팡 추천] {product['productName']}"
            if title_check not in existing:
                try:
                    post_to_wordpress(product)
                    time.sleep(2)
                except Exception as e:
                    print(f"오류: {e}")
        return

    if args.run_once:
        run_upload()
        return

    # 스케줄 모드
    print(f"⏰ 스케줄 모드: {SCHEDULE_HOURS}시간마다 자동 실행")
    run_upload()  # 시작 즉시 1회 실행
    schedule.every(SCHEDULE_HOURS).hours.do(run_upload)

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
