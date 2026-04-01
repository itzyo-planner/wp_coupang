# 쿠팡 파트너스 × 워드프레스 자동 업로드

쿠팡 파트너스 API로 상품을 검색하여 워드프레스에 자동으로 포스트를 올려주는 프로그램입니다.

## 설치

```bash
pip install -r requirements.txt
```

## 설정

`.env.example`을 복사해서 `.env` 파일을 만들고 값을 입력하세요.

```bash
cp .env.example .env
```

### 필수 설정값

| 항목 | 설명 |
|------|------|
| `COUPANG_ACCESS_KEY` | 쿠팡 파트너스 API Access Key |
| `COUPANG_SECRET_KEY` | 쿠팡 파트너스 API Secret Key |
| `COUPANG_AFFILIATE_ID` | 쿠팡 파트너스 Affiliate ID |
| `WP_URL` | 워드프레스 사이트 주소 |
| `WP_USERNAME` | 워드프레스 관리자 아이디 |
| `WP_APP_PASSWORD` | 워드프레스 앱 비밀번호 |

### 워드프레스 앱 비밀번호 발급
`워드프레스 관리자 → 사용자 → 프로필 → 애플리케이션 비밀번호`에서 생성

## 실행

### 스케줄 자동 실행 (기본)
```bash
python main.py
```

### 한 번만 실행
```bash
python main.py --run-once
```

### 특정 키워드로 즉시 실행
```bash
python main.py --keyword "무선이어폰"
```

## 파일 구조

```
wp_coupang/
├── main.py          # 메인 실행 파일
├── coupang_api.py   # 쿠팡 파트너스 API
├── wp_uploader.py   # 워드프레스 업로더
├── requirements.txt
├── .env.example
└── .gitignore
```

## 주의사항

- `.env` 파일은 절대 커밋하지 마세요
- 쿠팡 파트너스 API 사용량 제한을 확인하세요
- 워드프레스 REST API가 활성화되어 있어야 합니다
