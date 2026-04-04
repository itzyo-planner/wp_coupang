"""
일반글 자동 작성 모듈 (itzyo wp auto.py 핵심 로직 추출 - PyQt5 제거)
"""
import re
import json
import base64
import io
from urllib.parse import urlparse, urljoin
from typing import Optional, List, Dict, Tuple, Callable
import requests
from bs4 import BeautifulSoup
from markdown import markdown
from PIL import Image
from openai import OpenAI

# ── 상수 ──
SUMMARIZER_SYSTEM = """
당신은 웹문서/블로그 글 요약 전문가입니다.
아래 원문을 바탕으로 '새 글 재작성'에 필요한 핵심만 추출해 요약하세요.

요약 규칙:
- 원문 문장을 그대로 복사하지 말고, 의미만 재구성
- 핵심 주장/근거/데이터/주의사항/체크리스트/자주 나오는 포인트 위주
- 광고/군더더기/중복 제거
- 너무 짧게 말고, 재작성에 충분하도록 구체적으로

출력 포맷(반드시 유지):
[한줄핵심]
- ...

[핵심포인트]
- ...
- ...
- ...

[독자가 바로 할 일]
- ...
- ...
"""


# ── WordPress REST API ──

def wp_auth_headers(username: str, app_password: str) -> dict:
    app_password = app_password.replace(" ", "").strip()
    token = base64.b64encode(f"{username}:{app_password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def wp_upload_media(wp_base_url: str, auth_headers: dict, image_bytes: bytes, filename: str, alt_text: str) -> dict:
    media_url = wp_base_url.rstrip("/") + "/wp-json/wp/v2/media"
    files = {"file": (filename, image_bytes, "image/jpeg")}
    r = requests.post(media_url, headers=auth_headers, files=files, timeout=90)
    r.raise_for_status()
    media = r.json()
    try:
        requests.post(
            f"{media_url}/{media.get('id')}",
            headers={**auth_headers, "Content-Type": "application/json"},
            json={"alt_text": alt_text, "title": alt_text},
            timeout=30
        )
    except Exception:
        pass
    return {"id": media.get("id"), "source_url": media.get("source_url")}


def wp_create_post(wp_base_url: str, auth_headers: dict, title: str, html_content: str,
                   status: str = "draft", featured_media_id: Optional[int] = None) -> dict:
    posts_url = wp_base_url.rstrip("/") + "/wp-json/wp/v2/posts"
    payload = {"title": title, "content": html_content, "status": status}
    if featured_media_id:
        payload["featured_media"] = featured_media_id
    r = requests.post(posts_url, headers={**auth_headers, "Content-Type": "application/json"},
                      json=payload, timeout=90)
    r.raise_for_status()
    return r.json()


# ── Unsplash 이미지 검색 ──

def unsplash_get_image_jpeg(api_key: str, query: str) -> bytes:
    try:
        url = "https://api.unsplash.com/photos/random"
        params = {"query": query, "client_id": api_key, "orientation": "landscape"}
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        img_url = data.get("urls", {}).get("regular") or data.get("urls", {}).get("full")
        if not img_url:
            raise RuntimeError("이미지 URL 없음")
        img_resp = requests.get(img_url, timeout=60)
        img_resp.raise_for_status()
        image_obj = Image.open(io.BytesIO(img_resp.content))
        if image_obj.width > 800:
            ratio = 800 / image_obj.width
            image_obj = image_obj.resize((800, int(image_obj.height * ratio)), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image_obj.convert("RGB").save(out, format="JPEG", quality=65, optimize=True)
        return out.getvalue()
    except Exception as e:
        raise RuntimeError(f"Unsplash 이미지 가져오기 실패: {e}")


def insert_images_under_headings(html_content: str, image_urls: List[str]) -> str:
    soup = BeautifulSoup(html_content, "html.parser")
    idx = 0
    for h in soup.find_all(["h2", "h3"]):
        if idx >= len(image_urls):
            break
        heading_text = h.get_text(strip=True)
        if not heading_text:
            continue
        fig = soup.new_tag("figure", **{"class": "wp-block-image size-large"})
        img = soup.new_tag("img", src=image_urls[idx], alt=heading_text, loading="lazy")
        fig.append(img)
        h.insert_after(fig)
        idx += 1
    return str(soup)


# ── 크롤링 ──

def _extract_title(soup: BeautifulSoup, fallback: str) -> str:
    og = soup.select_one('meta[property="og:title"]')
    if og and og.get("content"):
        return og["content"].strip()
    t = soup.select_one("title")
    if t and t.get_text(strip=True):
        return t.get_text(strip=True)
    h1 = soup.select_one("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    return fallback


def _clean_text(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def crawl_url(url: str, platform: str = "general", log: Callable = None) -> Tuple[str, str, str]:
    """URL 크롤링 → (final_url, title, content_text)"""
    def _log(msg):
        if log:
            log(msg)

    _log(f"크롤링 중: {url}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    parsed = urlparse(url)

    # 네이버 블로그
    content_node = None
    if platform == "naver" or "blog.naver.com" in parsed.netloc:
        content_node = (
            soup.select_one("div.se-main-container") or
            soup.select_one("div#postViewArea") or
            soup.select_one("div.post-view")
        )
    # 티스토리
    elif platform == "tistory":
        content_node = (
            soup.select_one("div.entry-content") or
            soup.select_one("div.article") or
            soup.select_one("div.content")
        )

    # 일반
    if not content_node:
        content_node = (
            soup.select_one("article") or
            soup.select_one("main") or
            soup.select_one(".entry-content") or
            soup.select_one(".post-content") or
            soup.select_one(".article-content") or
            soup.select_one("div[itemprop='articleBody']") or
            soup.select_one("div#content")
        )

    if content_node:
        for tag in content_node(["script", "style", "nav", "header", "footer", "aside", "button", "form", "iframe"]):
            tag.decompose()
        content_text = content_node.get_text("\n", strip=True)
    else:
        body = soup.body
        if body:
            for tag in body(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
                tag.decompose()
            content_text = body.get_text("\n", strip=True)
        else:
            content_text = soup.get_text("\n", strip=True)

    content_text = _clean_text(content_text)
    title = _extract_title(soup, fallback=url.split("/")[-1] or "source")

    if len(content_text) < 200:
        raise ValueError(f"본문이 너무 짧습니다 ({len(content_text)}자). URL을 확인해주세요.")

    _log(f"크롤링 완료: {title} ({len(content_text)}자)")
    return url, title, content_text


# ── OpenAI 글 생성 ──

def chunk_text(text: str, max_chars: int = 8000) -> List[str]:
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


def summarize_text(client: OpenAI, text: str, log: Callable = None) -> str:
    chunks = chunk_text(text)
    partials = []
    for idx, ch in enumerate(chunks, 1):
        if log:
            log(f"요약 중... ({idx}/{len(chunks)})")
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SUMMARIZER_SYSTEM},
                {"role": "user", "content": ch}
            ]
        )
        partials.append((resp.choices[0].message.content or "").strip())

    if len(partials) == 1:
        return partials[0]

    if log:
        log("요약 합치는 중...")
    resp2 = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SUMMARIZER_SYSTEM},
            {"role": "user", "content": "\n\n---\n\n".join(partials)}
        ]
    )
    return (resp2.choices[0].message.content or "").strip()


def generate_from_summary(client: OpenAI, system_prompt: str, summary: str,
                           source_url: str, output_format: str = "html", log: Callable = None) -> str:
    from datetime import datetime
    if log:
        log("본문 작성 중...")
    current_date = datetime.now().strftime("%Y년 %m월 %d일")
    current_year = datetime.now().strftime("%Y")

    if output_format == "html":
        fmt = (
            "3. **[CRITICAL] HTML 포맷 엄격 준수**: 본문을 순수 HTML 태그로만 작성하세요.\n"
            "   - Markdown 문법 절대 금지. <h2>,<h3>,<p>,<ul>/<li>,<table>,<strong> 사용.\n"
        )
    else:
        fmt = (
            "3. **[CRITICAL] Markdown 포맷 엄격 준수**: HTML 태그 절대 금지.\n"
            "   - ## (H2), ### (H3), - (목록), **Bold** 사용.\n"
        )

    user_input = (
        f"현재 시점: {current_date}\n"
        f"올해={current_year}년, 내년={int(current_year)+1}년 기준으로 시제 조정.\n\n"
        "!!! 작성 지침 !!!\n"
        "1. 요약 금지 - 원본 내용을 충실히 반영하여 길고 자세하게 작성.\n"
        "2. 전문 블로거 톤으로 구조적 글쓰기.\n"
        f"{fmt}\n"
        "4. 외부 링크 3~5개 자연스럽게 포함 (정부/공공기관/언론사 등 신뢰 출처, 한국 사이트 우선).\n"
        f"5. 원본 링크({source_url})는 본문에 넣지 마세요.\n\n"
        f"[원본 내용]\n{summary}"
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]
    )
    return (resp.choices[0].message.content or "").strip()


def generate_title(client: OpenAI, title_prompt: str, original_title: str,
                   summary: str, log: Callable = None) -> str:
    from datetime import datetime
    if log:
        log("제목 생성 중...")
    current_date = datetime.now().strftime("%Y년 %m월 %d일")
    current_year = datetime.now().strftime("%Y")

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": title_prompt},
            {"role": "user", "content": (
                f"현재 시점: {current_date}, 올해={current_year}년\n"
                f"원본 제목: {original_title}\n\n요약:\n{summary}\n\n새 제목을 생성하세요."
            )}
        ]
    )
    t = (resp.choices[0].message.content or "").strip().strip('"\'')
    return t if t else original_title


def generate_thumbnail_concept(client: OpenAI, title: str) -> str:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a visual concept designer for blog thumbnails."},
            {"role": "user", "content": (
                f"블로그 제목: {title}\n"
                "이 제목에 어울리는 썸네일 이미지 컨셉을 영어로 간결하게 답하세요.\n"
                "형식: '[주요 객체1], [주요 객체2], [배경분위기]'"
            )}
        ],
        temperature=0.7
    )
    return (resp.choices[0].message.content or "").strip() or f"abstract {title}"


def extract_headings(html_content: str, h2_only: bool = False) -> List[str]:
    soup = BeautifulSoup(html_content, "html.parser")
    tags = ["h2"] if h2_only else ["h2", "h3"]
    return [h.get_text(strip=True) for h in soup.find_all(tags) if h.get_text(strip=True)]


def to_html(content: str) -> str:
    is_html = any(t in content.lower() for t in ["<h2", "<h3", "<p>", "<ul>"])
    return content if is_html else markdown(content)


# ── 전체 파이프라인 ──

def run_post_pipeline(
    source_url: str,
    source_text: str,
    system_prompt: str,
    title_prompt: str,
    openai_api_key: str,
    wp_url: str,
    wp_user: str,
    wp_pw: str,
    wp_status: str = "draft",
    output_format: str = "html",
    use_unsplash: bool = False,
    unsplash_api_key: str = "",
    max_images: int = 3,
    h2_only: bool = False,
    platform: str = "general",
    log: Callable = None,
) -> dict:
    """
    전체 파이프라인 실행
    Returns: {"status": "ok", "post_url": "...", "title": "..."}
    """
    def _log(msg):
        if log:
            log(msg)

    client = OpenAI(api_key=openai_api_key)
    auth = wp_auth_headers(wp_user, wp_pw)

    # 1) 크롤링 (URL인 경우)
    title = "새 글"
    if source_url and not source_text:
        source_url, title, source_text = crawl_url(source_url, platform=platform, log=_log)
    elif source_url:
        # 텍스트 직접 입력 + URL만 출처용
        title = source_url.split("/")[-1] or "새 글"

    # 2) 요약
    _log("내용 요약 중...")
    summary = summarize_text(client, source_text, log=_log)

    # 3) 제목 생성
    if title_prompt:
        title = generate_title(client, title_prompt, title, summary, log=_log)

    # 4) 본문 생성
    content_raw = generate_from_summary(
        client, system_prompt, summary, source_url or "",
        output_format=output_format, log=_log
    )
    html_content = to_html(content_raw)

    # 5) Unsplash 이미지
    featured_media_id = None
    if use_unsplash and unsplash_api_key:
        headings = extract_headings(html_content, h2_only=h2_only)[:max_images]
        image_urls = []

        # 썸네일 (대표 이미지)
        _log("썸네일 이미지 검색 중 (Unsplash)...")
        try:
            thumb_bytes = unsplash_get_image_jpeg(unsplash_api_key, title)
            media = wp_upload_media(wp_url, auth, thumb_bytes, f"thumb_{re.sub(r'[^a-z0-9]', '_', title.lower())[:30]}.jpg", title)
            featured_media_id = media["id"]
            _log(f"썸네일 업로드 완료: {media['source_url']}")
        except Exception as e:
            _log(f"썸네일 실패 (계속 진행): {e}")

        # 본문 이미지
        for i, heading in enumerate(headings):
            _log(f"이미지 검색 중 ({i+1}/{len(headings)}): {heading}")
            try:
                img_bytes = unsplash_get_image_jpeg(unsplash_api_key, heading)
                media = wp_upload_media(wp_url, auth, img_bytes, f"img_{i+1}.jpg", heading)
                image_urls.append(media["source_url"])
                _log(f"이미지 업로드: {media['source_url']}")
            except Exception as e:
                _log(f"이미지 {i+1} 실패 (스킵): {e}")

        if image_urls:
            html_content = insert_images_under_headings(html_content, image_urls)

    # 6) WordPress 업로드
    _log("워드프레스에 업로드 중...")
    result = wp_create_post(wp_url, auth, title, html_content, status=wp_status,
                            featured_media_id=featured_media_id)
    post_url = result.get("link", "")
    _log(f"업로드 완료: {post_url}")

    return {"status": "ok", "post_url": post_url, "title": title, "post_id": result.get("id")}
