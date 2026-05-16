# 올리브영 화장품 리뷰 크롤러

올리브영(oliveyoung.co.kr)의 **판매랭킹 상위 상품** 리뷰를 카테고리별로 수집해
JSONL 로 저장하는 크롤러.

> 기말 프로젝트 — 화장품 리뷰 데이터 수집 및 분석 파이프라인 구축

---

## 기술 스택

| 목적 | 라이브러리 |
|---|---|
| 브라우저 자동화 (판매랭킹·상품 페이지, 로그인) | Selenium 4.44 + undetected-chromedriver 3.5 |
| 리뷰 API 직접 호출 | requests 2.34 |
| 진행률 표시 | tqdm 4.67 |
| **Python** | **3.11** (conda env: `oliveyoung`) |

---

## 환경 설정

```bash
conda create -n oliveyoung python=3.11
conda activate oliveyoung
pip install -r requirements.txt
```

로그인은 **선택**이다(아래 "왜 로그인이 선택인가" 참고). 로그인하려면:

```bash
set OY_ID=올리브영아이디
set OY_PW=비밀번호
```

---

## 실행

```bash
# 단일 카테고리
python main.py --category skincare --max-products 100

# 전체 카테고리(skincare·maskpack·cleansing·suncare) 순회
python main.py --category all --max-products 100 --no-login

# 중단(429 등) 후 같은 명령 재실행 → 완료 상품은 건너뛰고 이어서 수집
python main.py --category all --max-products 100 --no-login
```

| 인자 | 설명 |
|---|---|
| `--category` | `skincare` / `maskpack` / `cleansing` / `suncare` / `all` |
| `--max-products` | 카테고리당 최대 상품 수 (판매랭킹 천장 100) |
| `--no-login` | 로그인·수동 프롬프트 건너뜀 (무인·밤샘 실행 권장) |

출력: `output/{category}_reviews.jsonl` (JSONL, UTF-8)

---

## 수집 데이터 스키마

```
platform        고정값 "oliveyoung"
product_id      상품 고유번호 (goodsNo)
review_id       리뷰 고유번호 (중복 제거 키)
product_name    상품명
brand           브랜드명
category        skincare | maskpack | cleansing | suncare
price           판매가 (원, 정수) — 없으면 null
rating          별점 (1.0~5.0)
review_text     리뷰 본문
review_date     작성일 (YYYY-MM-DD)
skin_type       피부타입 (건성/복합성/지성/민감성/중성)
skin_concern    피부고민 (미백, 모공, 트러블 … 복수)
reviewer_age    나이대 (API 미제공 → null)
helpful_count   도움이요 수
photo_exists    사진 첨부 여부
crawled_at      수집 일시
raw_url         상품 페이지 URL
```

---

## 디렉터리 구조

```
oliveyoung_crawler/
├── main.py            # 진입점 — 오케스트레이션만(흐름이 그대로 읽힘)
├── config.py          # 모든 상수 (URL·정렬·재시도·딜레이·게이트 기준)
├── schema.py          # ReviewSchema dataclass (JSONL 1줄 = 리뷰 1개)
├── browser.py         # OliveYoungBrowser — 드라이버 생성/종료만
├── auth.py            # OliveYoungAuth — (선택) 로그인 + 쿠키 복사
├── storage.py         # ReviewStorage — JSONL append, 중복/이어받기 관리
└── crawlers/
    ├── category.py    # CategoryCrawler — 판매랭킹 → 상품 URL 목록
    ├── product.py     # ProductCrawler  — 상품 페이지 → 메타데이터
    └── review.py      # ReviewCrawler   — 리뷰 API(커서) 호출·파싱
```

각 클래스는 역할이 하나다. 크롤러끼리 서로 import 하지 않고
`config`/`schema` 만 공유한다.

---

## 수집 전략 & 설계 고민

### 왜 Selenium + requests 혼용?

- **판매랭킹·상품 페이지**: JS 렌더링이 필요해 Selenium 으로 연다.
- **리뷰**: 모바일 API `m.oliveyoung.co.kr/review/api/v2/reviews/cursor` 를
  requests 로 직접 호출 — 페이지를 안 열어 훨씬 빠르고 부하가 낮다.

### 왜 "판매랭킹"에서 상품을 고르나?

그냥 카테고리 목록은 정렬 기준이 불분명하다. 판매랭킹은 **잘 팔리는 =
검증된 상품**이 위쪽에 모이므로, 분석 가치가 높은 상품을 자연스럽게 고를 수
있다. `getBestList.do?dispCatNo=900000100100001&fltDispCatNo={코드}` 가
카테고리별 상위 100개를 한 페이지에 준다(페이지네이션 불필요).

### 품질 게이트 (리뷰 수 필터)

랭킹 상위라도 리뷰가 적으면 분석용으로 부실하다. 상세 페이지를 열기 **전에**
통계 API(`reviews/{goodsNo}/stats`)로 리뷰 수만 싸게 확인해
`MIN_REVIEW_COUNT`(기본 100) 미만이면 건너뛴다. Selenium 낭비도 없앤다.

### 왜 커서 페이지네이션인가?

이 API 는 `page` 번호를 무시한다(`page=1,2,3` 다 같은 첫 페이지 반환).
응답의 `nextCursorId/Score/Count` 를 다음 요청의 `cursorId/Score/Count` 로
넘기는 **커서 방식**이라야 다음 리뷰가 나온다. 정렬 5종(유용한순·최신순·
도움순·평점높은순·평점낮은순)을 각각 커서로 끝까지 돌려 합친 뒤
`review_id` 로 중복을 제거한다 → 상품당 보통 300+ 개.

### 왜 로그인이 "선택"인가?

비로그인도 커서로 **정렬당 ~100개**까지 받을 수 있어, 정렬 5종 합치면
상품당 300+ 라는 목표가 로그인 없이 달성된다. 로그인하면 정렬당 100개
이상도 가능하지만, 대량 수집 시 rate limit 위험이 커진다. 그래서 무인
실행은 `--no-login` 을 권장한다.

### 중단/재시작 안전 (이어받기)

리뷰는 **상품 단위로 한 번에** 저장된다(수집 중 429 면 그 상품은 한 줄도
안 들어간다). 따라서 JSONL 에 `product_id` 가 있으면 그 상품은 "완료"다.
재실행 시 완료 상품은 **API 호출 없이 즉시 건너뛰고** 멈춘 지점부터
이어서 수집한다 → 429 로 끊겨도 같은 명령만 다시 돌리면 된다.

### rate limit(429) 대응

429 는 재시도해도 소용없으므로 즉시 멈추고(`RateLimitError`) 그때까지를
저장한다. 요청량/IP 기준 일시 차단이라 보통 수 시간 내 회복되며, 그 뒤
같은 명령으로 이어받기 하면 된다. 요청 간 랜덤 sleep 으로 속도를 조절한다
(`config.py` 의 `SLEEP_*`).

---

## 한계 / 알아둘 점

- 판매랭킹 천장은 카테고리당 100개. 랭킹은 매일 바뀌므로 여러 세션에 걸쳐
  돌리면 누적 상품 수가 100을 넘을 수 있다(다양성에는 이득).
- 10만 건 규모는 한 번에 불가능 — 429 가 세션을 끊으므로 여러 번 나눠
  이어받기로 모은다.
- 통계 API 의 리뷰 수와 실제 커서로 받히는 수가 다른 상품이 드물게 있다.
