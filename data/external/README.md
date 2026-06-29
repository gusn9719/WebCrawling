# data/external — 외부 플랫폼 데이터

Musinsa와 Coupang의 화장품 리뷰 데이터를 외부 CSV 형태로 수집하여 공통 스키마로 변환했다.

---

## 플랫폼별 데이터 현황

| 플랫폼 | 전체 리뷰 건수 | base_skin_type 있는 비율 | skin_concern |
|---|---|---|---|
| OliveYoung | ~270K | 39.3% | 있음 (17.3%) |
| Musinsa | ~100K | 62.9% | 없음 |
| Coupang | ~32K | **0.0%** | 없음 |

**Coupang은 skin_type 컬럼이 없어서 피부타입 기반 추천에서 전체 제외된다.**

---

## 변환 도구

```bash
python normalize_external.py
```

입력: 각 플랫폼의 원본 CSV 파일  
출력: `output_external/musinsa_reviews.jsonl`, `output_external/coupang_reviews.jsonl`

---

## 플랫폼별 입력 컬럼 구조

### Musinsa

| 원본 컬럼 | 공통 스키마 컬럼 | 변환 내용 |
|---|---|---|
| rating | rating | 그대로 |
| review | review_text | 그대로 |
| skin_type | skin_type | 그대로 |
| date | review_date | '26.05.04' → '2026-05-04' 변환 |
| product_id | product_id | 그대로 |
| product_name | product_name | 그대로 |
| brand | brand | 그대로 |

review_id: SHA256 해시 생성 (platform + product_id + 리뷰 텍스트 앞 100자 기준)

### Coupang

| 원본 컬럼 | 공통 스키마 컬럼 | 변환 내용 |
|---|---|---|
| 평점 | rating | 그대로 |
| 리뷰내용 | review_text | 그대로 |
| 작성일 | review_date | Excel 일련번호 → datetime 변환 |
| 상품명 | product_name | 그대로 |
| 브랜드 | brand | 그대로 |

skin_type: 없음 (Coupang API에 없음, null로 채움)  
review_id: SHA256 해시 생성  
Coupang 원본 CSV가 4개 분할 파일로 나뉜 경우 → `normalize_external.py`가 자동으로 병합

---

## 변환 후 공통 스키마

| 컬럼 | 타입 | 설명 |
|---|---|---|
| platform | str | "musinsa" / "coupang" |
| product_id | str | 플랫폼 내 상품 ID (또는 해시) |
| product_name | str | 상품명 |
| brand | str | 브랜드명 |
| category | str | 플랫폼에서 분류한 카테고리 (있을 경우) |
| rating | float | 별점 (1.0~5.0) |
| review_text | str | 리뷰 원문 |
| skin_type | str | 사용자 입력 피부타입 (null 가능) |
| skin_concern | str | 피부 고민 (null, 외부 플랫폼에 없음) |
| review_id | str | SHA256 해시 기반 고유 ID |

---

## 원본 CSV 제외 이유

Musinsa/Coupang 원본 CSV 파일은 이 저장소에 포함되지 않는다.

이유:
- 원본 CSV의 저작권 및 배포 조건 미확인
- 파일 크기 (Musinsa: ~200MB, Coupang: ~100MB)

원본 CSV가 있으면 위 변환 명령으로 JSONL로 변환하여 전처리에 사용할 수 있다.

---

## Coupang 피부타입 기반 집계 제외

`product_recommendation_scores.parquet` 생성 시 피부타입 기반 집계는 OliveYoung + Musinsa 데이터만 사용한다.

Coupang 데이터는 일반 상품 추천 탭(탭1/2)에서는 사용되며, 피부타입별 부정 신호 비율 집계에서만 제외된다.
