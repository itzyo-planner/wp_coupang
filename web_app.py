"""
쿠팡 파트너스 × 워드프레스 웹 대시보드
"""
from flask import Flask, render_template, request, jsonify, redirect, url_for
import threading
import json
import os
import time
from datetime import datetime
from dotenv import load_dotenv, set_key

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# 업로드 로그 (메모리)
upload_logs = []
is_running = False
run_thread = None


def add_log(message, level="info"):
    upload_logs.append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": message,
        "level": level
    })
    if len(upload_logs) > 200:
        upload_logs.pop(0)


def run_upload_task(keywords, limit):
    global is_running
    is_running = True
    try:
        from coupang_api import get_best_products
        from wp_uploader import post_to_wordpress, get_existing_post_titles

        add_log("업로드 작업 시작", "info")
        existing = get_existing_post_titles()
        add_log(f"기존 포스트 {len(existing)}개 확인", "info")

        uploaded = 0
        for keyword in keywords:
            if not is_running:
                break
            add_log(f"키워드 검색: '{keyword}'", "info")
            try:
                products = get_best_products(keyword, limit=limit)
                for product in products:
                    if not is_running:
                        break
                    title = f"[쿠팡 추천] {product['productName']}"
                    if title in existing:
                        add_log(f"중복 스킵: {product['productName'][:30]}...", "warning")
                        continue
                    post_to_wordpress(product)
                    existing.add(title)
                    uploaded += 1
                    add_log(f"업로드 완료: {product['productName'][:40]}", "success")
                    time.sleep(2)
            except Exception as e:
                add_log(f"오류 [{keyword}]: {str(e)}", "error")

        add_log(f"작업 완료: 총 {uploaded}개 업로드", "success")
    except Exception as e:
        add_log(f"치명적 오류: {str(e)}", "error")
    finally:
        is_running = False


@app.route("/")
def index():
    env = {
        "WP_URL": os.getenv("WP_URL", ""),
        "WP_USERNAME": os.getenv("WP_USERNAME", ""),
        "COUPANG_ACCESS_KEY": os.getenv("COUPANG_ACCESS_KEY", ""),
        "COUPANG_AFFILIATE_ID": os.getenv("COUPANG_AFFILIATE_ID", ""),
        "POSTS_PER_RUN": os.getenv("POSTS_PER_RUN", "5"),
        "SCHEDULE_INTERVAL_HOURS": os.getenv("SCHEDULE_INTERVAL_HOURS", "6"),
        "POST_STATUS": os.getenv("POST_STATUS", "publish"),
    }
    keywords_raw = os.getenv("KEYWORDS", "노트북,무선이어폰,공기청정기,전기밥솥,스마트워치")
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
    return render_template("index.html", env=env, keywords=keywords,
                           is_running=is_running, logs=upload_logs[-50:])


@app.route("/api/start", methods=["POST"])
def api_start():
    global is_running, run_thread
    if is_running:
        return jsonify({"status": "error", "message": "이미 실행 중입니다."})

    data = request.json or {}
    keywords = data.get("keywords", ["노트북"])
    limit = int(data.get("limit", 5))

    run_thread = threading.Thread(target=run_upload_task, args=(keywords, limit), daemon=True)
    run_thread.start()
    return jsonify({"status": "ok", "message": "업로드 시작!"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    global is_running
    is_running = False
    add_log("사용자가 작업을 중지했습니다.", "warning")
    return jsonify({"status": "ok", "message": "중지 요청됨"})


@app.route("/api/logs")
def api_logs():
    offset = int(request.args.get("offset", 0))
    return jsonify({
        "logs": upload_logs[offset:],
        "total": len(upload_logs),
        "is_running": is_running
    })


@app.route("/api/clear-logs", methods=["POST"])
def api_clear_logs():
    upload_logs.clear()
    return jsonify({"status": "ok"})


@app.route("/api/settings", methods=["POST"])
def api_settings():
    data = request.json or {}
    env_path = os.path.join(os.path.dirname(__file__), ".env")

    if not os.path.exists(env_path):
        open(env_path, "w").close()

    fields = [
        "WP_URL", "WP_USERNAME", "WP_APP_PASSWORD",
        "COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_AFFILIATE_ID",
        "POSTS_PER_RUN", "SCHEDULE_INTERVAL_HOURS", "POST_STATUS",
        "POST_CATEGORY_ID", "KEYWORDS"
    ]
    for field in fields:
        if field in data and data[field]:
            set_key(env_path, field, str(data[field]))
            os.environ[field] = str(data[field])

    return jsonify({"status": "ok", "message": "설정 저장 완료!"})


@app.route("/api/status")
def api_status():
    return jsonify({
        "is_running": is_running,
        "log_count": len(upload_logs),
        "wp_url": os.getenv("WP_URL", "미설정"),
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")
