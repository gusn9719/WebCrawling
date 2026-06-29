# data/raw — OliveYoung 수집 원본 데이터

원본 JSONL 파일은 GitHub Releases에서 제공한다. 이 폴더에 배치하거나 `output/` 경로를 사용한다.

---

## 수집 플랫폼

OliveYoung (`https://www.oliveyoung.co.kr`)

---

## 수집 카테고리

| 카테고리 | 필터 코드 | 산출 파일 |
|---|---|---|
| skincare | 10000010001 | `output/skincare_reviews.jsonl` |
| maskpack | 10000010009 | `output/maskpack_reviews.jsonl` |
| cleansing | 10000010010 | `output/cleansing_reviews.jsonl` |
| suncare | 10000010011 | `output/suncare_reviews.jsonl` |

---

## 수집 방식

**Selenium (헤드풀) + requests (모바일 API) 하이브리드**

| 역할 | 도구 | 이유 |
|---|---|---|
| 판매랭킹 페이지 로딩, 상품 URL 수집 | Selenium (Chrome, headless=False) | JS 렌더링 필요 |
| 상품 상세 페이지 로딩 | Selenium (Chrome, headless=False) | JS 렌더링 필요 |
| 리뷰 데이터 수집 | requests (모바일 API) | JSON 직접 응답 |

headless=True 모드는 OliveYoung이 봇으로 감지해 페이지를 차단한다. 실제 Chrome 창이 열리는 헤드풀 모드에서만 정상 동작한다.

---

## 커서 기반 페이지네이션

리뷰 API는 커서 방식으로만 동작한다.

- **엔드포인트**: `POST https://m.oliveyoung.co.kr/review/api/v2/reviews/cursor`
- 응답의 `nextCursorId / nextCursorScore / nextCursorCount` → 다음 요청 파라미터로 전달
- `hasNext=false`가 될 때까지 반복
- 필수 헤더: `Origin: https://www.oliveyoung.co.kr`, `Referer: https://www.oliveyoung.co.kr/`

---

## 상품 선정 기준

판매랭킹 URL에서 카테고리별 상위 100개 상품을 수집한다.  
수집 전 리뷰 수를 먼저 조회하여 **MIN_REVIEW_COUNT=100 미만 상품은 제외** (품질 게이트).

---

## rate limit 처리

약 70개 상품(~2.5시간) 수집 후 HTTP 429 응답 발생.  
재시도는 무의미하므로 즉시 중단한다. 수 시간 후 같은 명령으로 재실행하면 완료된 상품을 건너뛰고 이어서 수집한다.

---

## JSONL 스키마 (각 줄이 리뷰 1건)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| platform | str | "oliveyoung" |
| product_id | str | 상품 고유 ID |
| product_name | str | 상품명 |
| brand | str | 브랜드명 |
| category | str | skincare / maskpack / cleansing / suncare |
| rating | float | 별점 (1.0~5.0) |
| review_text | str | 리뷰 원문 |
| skin_type | str | 사용자 선택 피부타입 (null 가능) |
| skin_concern | str | 피부 고민 (null 가능, OliveYoung 전용) |
| raw_url | str | 상품 페이지 URL |
| review_id | str | 리뷰 고유 ID |

---

## 수집 현황

| 카테고리 | 수집 상품 수 | 리뷰 건수 | 파일 크기 |
|---|---|---|---|
| skincare | 100 | ~170K | 42.6MB |
| maskpack | 100 | ~70K | ~30MB |
| cleansing | 100 | ~12K | ~2MB |
| suncare | 100 | ~18K | ~12MB |
| **전체** | ~400 | **~270K** | **~87MB** |

---

## 한계

- 비로그인 수집 (로그인 없이도 모든 리뷰 접근 가능)
- headless 모드 불가 → 자동화 환경에서 크롤링 어려움
- rate limit (429)으로 단일 세션에서 전체 수집 불가 (여러 세션으로 나눠 수집)
- skin_type 있는 리뷰 비율: 약 39.3% (나머지는 피부타입 정보 없음)
- skin_concern 있는 리뷰: 전체의 약 17.3%

---

## 재수집 명령

```bash
conda activate oliveyoung

# 전체 카테고리 수집
python main.py --category all --max-products 100

# 단일 카테고리
python main.py --category skincare --max-products 100
```

---

## Releases 다운로드

GitHub Releases에서 `oliveyoung_raw_data_v3.tar.gz`를 다운로드 후:

```bash
# 압축 해제 → output/ 폴더에 *.jsonl 파일들 배치됨
tar xzf oliveyoung_raw_data_v3.tar.gz
```
