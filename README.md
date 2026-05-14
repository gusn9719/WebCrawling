# 올리브영 화장품 리뷰 크롤러

올리브영(oliveyoung.co.kr) 스킨케어·선케어·메이크업 카테고리의  
상품 정보와 리뷰를 수집해 JSONL 형식으로 저장하는 크롤러.

기말 프로젝트 — 화장품 리뷰 데이터 수집 및 분석 파이프라인 구축

---

## 기술 스택

| 목적 | 라이브러리 |
|---|---|
| 브라우저 자동화 (카테고리·상품 탐색, 로그인) | Selenium 4.44 |
| 리뷰 API 호출 | requests 2.34 |
| ChromeDriver 자동 설치 | webdriver-manager 4.0 |
| 진행률 표시 | tqdm 4.67 |
| **Python** | **3.11.15** |

---

## 환경 설정

```bash
# 1. conda 가상환경 생성
conda create -n oliveyoung python=3.11
conda activate oliveyoung

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 로그인 정보 환경변수 등록 (선택 — 로그인 없이도 동작, 단 상품당 10개 한계)
set OY_ID=올리브영아이디
set OY_PW=비밀번호
```

---

## 실행

```bash
# 기본 실행 (스킨케어 100개 상품)
python main.py --category skincare --max-products 100

# 전체 카테고리 대량 수집
python main.py --category skincare --max-products 500
python main.py --category suncare  --max-products 300
python main.py --category makeup   --max-products 500

# 중단 후 재시작 → 이미 수집한 review_id 자동 skip
python main.py --category skincare --max-products 500
```

---

## 수집 데이터 스키마

```
platform        고정값 "oliveyoung"
product_id      상품 고유번호 (goodsNo)
review_id       리뷰 고유번호
product_name    상품명
brand           브랜드명
category        skincare | suncare | makeup
price           판매가 (원, 정수)
rating          별점 (1.0~5.0)
review_text     리뷰 본문
review_date     작성일 (YYYY-MM-DD)
skin_type       피부타입 (건성/복합성/지성/민감성/중성)
skin_concern    피부고민 (미백, 모공, 트러블 등 복수)
reviewer_age    나이대 (API 미제공 → null)
helpful_count   도움이요 수
photo_exists    사진 첨부 여부
crawled_at      수집 일시
raw_url         상품 페이지 URL
```

저장 형식: `output/{category}_reviews.jsonl` (JSONL, UTF-8)

---

## 디렉터리 구조

```
oliveyoung_crawler/
├── config.py          # URL, 수집 전략 상수
├── browser.py         # Chrome headless 설정, 봇 감지 우회
├── auth.py            # 올리브영 로그인 (Selenium)
├── schema.py          # ReviewSchema dataclass
├── crawlers/
│   ├── category.py    # 카테고리 페이지 → 상품 URL 목록
│   ├── product.py     # 상품 페이지 → 상품명/브랜드/가격
│   └── review.py      # 리뷰 API 호출 (커서 기반 페이지네이션)
├── storage.py         # JSONL append, 중복 체크, 재시작 안전
└── main.py            # 진입점 (argparse + tqdm)
```

---

## 수집 전략 & 설계 고민

### 왜 Selenium + requests 혼용?

- **카테고리·상품 페이지**: React SSR이라 JS 렌더링 필요 → Selenium
- **리뷰 API**: `m.oliveyoung.co.kr/review/api/v2/reviews/cursor` 직접 호출 가능  
  → requests가 훨씬 빠르고 서버 부하 낮음

### 왜 로그인이 필요한가?

비로그인 상태에서 리뷰 API는 상품당 10개만 반환하고 `hasNext=false`로 잠근다.  
Selenium으로 로그인 후 세션 쿠키를 requests에 전달하면 커서 페이지네이션이 열린다.

### 상품당 수집 한계를 왜 설정하나?

달바 미스트처럼 리뷰 47,000건인 상품에서 전부 수집하면  
한 상품에 몇 시간이 걸리고 데이터 편향이 발생한다.  
→ 상품당 200개 상한 + 도움순/최신순/낮은 평점순 균등 분배로 다양성 확보.

### 봇 차단 우회 전략

- `navigator.webdriver` CDP로 제거
- 요청 간 random sleep (1.5~3초)
- 1시간마다 3~5분 휴식 (장시간 운영 시)
- 올리브영은 Akamai 미사용 — Coupang 대비 완화된 환경

---

## 진행 기록

| 날짜 | 내용 |
|---|---|
| 2026-05-14 | 프로젝트 초기화, 기본 파이프라인 구현 |
| 2026-05-14 | 실제 DOM/API 확인: `ul.cate_prd_list`, 리뷰 API `m.oliveyoung.co.kr/review/api/v2/reviews/cursor` |
| 2026-05-14 | 커서 기반 페이지네이션 구현 (nextCursorId/Score/Count) |
| 2026-05-14 | 비로그인 한계(10개) 확인 → 로그인 모듈 추가 예정 |
