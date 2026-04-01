"""
쿠팡 파트너스 × 워드프레스 웹 대시보드
"""
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from functools import wraps
import threading
import hashlib
import secrets
import json
import os
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── 설정 파일 (로컬: .env / 클라우드: config.json) ──
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    """config.json 로드 (없으면 빈 dict)"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_config(data: dict):
    """config.json 저장 + 환경변수 동기화"""
    cfg = load_config()
    cfg.update(data)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    for k, v in data.items():
        os.environ[k] = str(v)

def get_cfg(key: str, default: str = "") -> str:
    """환경변수 → config.json 순으로 읽기"""
    return os.getenv(key) or load_config().get(key, default)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)


# ── 인증 ──
def get_password_hash():
    pw = os.getenv("DASHBOARD_PASSWORD", "")
    if not pw:
        return None
    return hashlib.sha256(pw.encode()).hexdigest()

def check_password(password: str) -> bool:
    stored = get_password_hash()
    if not stored:
        return True  # 비밀번호 미설정 시 로컬에서만 접근 가능하도록 허용
    return hashlib.sha256(password.encode()).hexdigest() == stored

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            if request.is_json:
                return jsonify({"status": "error", "message": "인증 필요"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

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


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        pw = request.form.get("password", "")
        if check_password(pw):
            session["logged_in"] = True
            session.permanent = True
            return redirect(url_for("index"))
        error = "비밀번호가 틀렸습니다."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    env = {
        "WP_URL": get_cfg("WP_URL"),
        "WP_USERNAME": get_cfg("WP_USERNAME"),
        "COUPANG_ACCESS_KEY": get_cfg("COUPANG_ACCESS_KEY"),
        "COUPANG_AFFILIATE_ID": get_cfg("COUPANG_AFFILIATE_ID"),
        "POSTS_PER_RUN": get_cfg("POSTS_PER_RUN", "5"),
        "SCHEDULE_INTERVAL_HOURS": get_cfg("SCHEDULE_INTERVAL_HOURS", "6"),
        "POST_STATUS": get_cfg("POST_STATUS", "publish"),
        "POST_CATEGORY_ID": get_cfg("POST_CATEGORY_ID", "1"),
    }
    keywords_raw = get_cfg("KEYWORDS", "노트북,무선이어폰,공기청정기,전기밥솥,스마트워치")
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
    return render_template("index.html", env=env, keywords=keywords,
                           is_running=is_running, logs=upload_logs[-50:])


@app.route("/api/start", methods=["POST"])
@login_required
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
@login_required
def api_stop():
    global is_running
    is_running = False
    add_log("사용자가 작업을 중지했습니다.", "warning")
    return jsonify({"status": "ok", "message": "중지 요청됨"})


@app.route("/api/logs")
@login_required
def api_logs():
    offset = int(request.args.get("offset", 0))
    return jsonify({
        "logs": upload_logs[offset:],
        "total": len(upload_logs),
        "is_running": is_running
    })


@app.route("/api/clear-logs", methods=["POST"])
@login_required
def api_clear_logs():
    upload_logs.clear()
    return jsonify({"status": "ok"})


@app.route("/api/settings", methods=["POST"])
@login_required
def api_settings():
    data = request.json or {}
    allowed = [
        "WP_URL", "WP_USERNAME", "WP_APP_PASSWORD",
        "COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_AFFILIATE_ID",
        "POSTS_PER_RUN", "SCHEDULE_INTERVAL_HOURS", "POST_STATUS",
        "POST_CATEGORY_ID", "KEYWORDS"
    ]
    to_save = {k: v for k, v in data.items() if k in allowed and v}
    if to_save:
        save_config(to_save)
    return jsonify({"status": "ok", "message": "설정 저장 완료!"})


@app.route("/api/status")
@login_required
def api_status():
    return jsonify({
        "is_running": is_running,
        "log_count": len(upload_logs),
        "wp_url": os.getenv("WP_URL", "미설정"),
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV") == "development"
    app.run(debug=debug, port=port, host="0.0.0.0")
