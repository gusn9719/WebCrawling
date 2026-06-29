# Service Reviews Check Report

생성일: 2026-06-27

## 1. 기본 수치

| 항목 | 값 |
| --- | --- |
| train row 수 | 321,950 |
| val row 수 | 80,488 |
| merge 전 전체 row 수 | 402,438 |
| merge 후 전체 row 수 | 402,438 |
| review_id 중복 수 | 0 |
| lstm_v3_pred 결측 수 | 0 |
| predicted_sentiment 예외값 수 | 0 |
| service_reviews.parquet row 수 (재로드) | 402,438 |
| product_key 결측 수 | 0 |
| predicted_sentiment 결측 수 (재로드 후) | 0 |

## 2. 저장 후 검증 결과

- 재로드 row 수: 402,438
- review_id 중복: 0
- predicted_sentiment 고유값: ['negative', 'neutral', 'positive']
- predicted_sentiment 3종 한정: ✓
- base_skin_type ok: 189,665 / no_base: 831 / missing: 211,942
- no_base_skin_type 831건 일치: ✓

**보호 파일 mtime 변경 없음 ✓**

## 3. 감성 예측 결합 결과

### predicted_sentiment 분포

| 값 | 수 |
| --- | --- |
| positive | 330,159 |
| neutral | 36,479 |
| negative | 35,800 |

### sentiment_label 분포

| 값 | 수 |
| --- | --- |
| positive | 352,240 |
| negative | 37,409 |
| neutral | 12,789 |

### 불일치 수: 33,454건 (8.31%)

## 4. 피부 타입 정규화 결과

### base_skin_type 분포

| base_skin_type | 수 |
| --- | --- |
| nan | 212,773 |
| 복합성 | 74,016 |
| 지성 | 58,062 |
| 건성 | 37,605 |
| 민감성 | 18,974 |
| 중성 | 1,008 |

### skin_type_normalization_status 분포

| status | 수 |
| --- | --- |
| missing | 211,942 |
| ok | 189,665 |
| no_base_skin_type | 831 |

- has_base_skin_type: 189,665건 (47.1%)
- no_base_skin_type: 831건
- missing: 211,942건

### 플랫폼별 base_skin_type 커버리지

| 플랫폼 | has_base | 전체 | 비율 |
| --- | --- | --- | --- |
| oliveyoung | 67,606 | 172,109 | 39.3% |
| musinsa | 122,059 | 194,144 | 62.9% |
| coupang | 0 | 36,185 | 0.0% |

## 5. 피부 고민 정규화 결과

### skin_concern_normalization_status 분포

| status | 수 |
| --- | --- |
| missing | 332,831 |
| ok | 66,884 |
| code_only | 2,723 |

- has_skin_concern_tags: 66,884건 (16.6%)

### 플랫폼별 skin_concern_tags 커버리지

| 플랫폼 | has_tags | 전체 | 비율 |
| --- | --- | --- | --- |
| oliveyoung | 66,884 | 172,109 | 38.9% |
| musinsa | 0 | 194,144 | 0.0% |
| coupang | 0 | 36,185 | 0.0% |

### skin_concern_codes 상위 20

| 코드 | 수 |
| --- | --- |
| C09 | 6,279 |
| C10 | 2,358 |
| C11 | 2,061 |
| C13 | 1,298 |
| C12 | 545 |

## 6. 서비스 관점 수치

### 플랫폼별 리뷰 수

| 플랫폼 | 수 |
| --- | --- |
| musinsa | 194,144 |
| oliveyoung | 172,109 |
| coupang | 36,185 |

### 카테고리별 리뷰 수 (상위 20)

| 카테고리 | 수 |
| --- | --- |
| beauty | 230,329 |
| skincare | 53,036 |
| maskpack | 45,161 |
| cleansing | 40,534 |
| suncare | 33,378 |

### product_key 수: 2,221

### product_key별 리뷰 수 분포

- min: 1
- max: 11221
- mean: 181.2
- median: 113.0

### base_skin_type별 predicted_sentiment 분포

| base_skin_type | negative | neutral | positive |
| --- | --- | --- | --- |
| 복합성 | 2,253 | 4,882 | 66,881 |
| 민감성 | 1,136 | 1,543 | 16,295 |
| 건성 | 1,743 | 2,747 | 33,115 |
| 지성 | 3,169 | 4,749 | 50,144 |
| 중성 | 124 | 113 | 771 |

### base_skin_type별 negative 리뷰 수

| base_skin_type | negative 수 |
| --- | --- |
| 건성 | 1,743 |
| 민감성 | 1,136 |
| 복합성 | 2,253 |
| 중성 | 124 |
| 지성 | 3,169 |

### 플랫폼별 negative 리뷰 수

| 플랫폼 | negative 수 |
| --- | --- |
| oliveyoung | 28,575 |
| coupang | 4,755 |
| musinsa | 2,470 |

## 7. 품질 판단

### Step 3 product_skin_aggregates 생성 가능 여부

- 가능: has_base_skin_type=True이고 predicted_sentiment가 있는 row 사용
- 제외 조건: base_skin_type is None (no_base_skin_type 831건 + missing 전체)

### 피부 타입 집계에서 제외해야 할 row 조건

- `has_base_skin_type == False` 모두 제외
- coupang 플랫폼: skin_type 없으므로 전체 has_base_skin_type=False

### 추천 점수 산정 시 주의할 점

- predicted_sentiment는 BiLSTM 예측 (macro_f1 0.666, neutral_recall 0.586 — neutral 성능 낮음)
- sentiment_label(약한 라벨)과의 불일치 비율을 UI에서 참고할 것
- 부정 리뷰 탐색 서비스이므로 negative recall이 핵심 지표

### 부정 리뷰 탐색 UI에서 사용할 수 있는 컬럼

- 필터: `base_skin_type`, `predicted_sentiment == 'negative'`, `product_key`, `platform`
- 표시: `review_text`, `rating`, `review_date`, `brand`, `product_name`, `category`
- 보조 표시: `skin_type_tags`, `skin_need_tags`, `skin_concern_tags`

### 아직 위험한 부분

- C09/C10/C11/C12/C13 코드 의미 미확인 → skin_concern_codes는 UI 직접 노출 금지
- neutral 예측 recall 0.586 → neutral 리뷰의 오분류 가능
- coupang 전체 base_skin_type 없음 → 피부 타입별 집계 불가

## 수동 샘플 검수 결과

- 직접 확인한 샘플 수: 181개 (그룹별 20개 × 9그룹 + platform_samples 21개)
- 확인한 파일: reports/service_reviews_manual_review_samples.csv
- 샘플링 그룹: merge_check_samples, negative_review_samples, positive_review_samples,
  neutral_review_samples, base_skin_type_samples, no_base_skin_type_samples,
  missing_skin_type_samples, skin_concern_code_samples, platform_samples, mismatch_samples

### 정상으로 판단한 예시

- negative 정확 판정: "트러블난거 진정시키느라 1주일 넘게 걸렸어요 재구매의사 없습니다" (rating=1)
- negative 정확 판정: "다른 화장품 사용하니 피부 문제가 해결됐네요 이건 무슨 의미일까 제품이 별로라는 거겠죠" (rating=1)
- no_base_skin_type 정상: skin_type="진정/보습 · 모공 · 여드름" → base=None, skin_need_tags=['진정', '보습', '모공', '트러블']
- platform 정상: musinsa base_skin_type 있음, coupang 전체 missing (예상 동작)
- base_skin_type 정상: 지성/건성/민감성/복합성 모두 확인됨

### 이상하거나 애매한 예시

- rating=4, label=positive, pred=negative: "자극없는데 눈에 들어가면 따가워요 그냥 다이소 토너 사서 쓸듯" → label은 positive지만 텍스트 뉘앙스는 부정. BiLSTM 판정이 더 정확.
- rating=5, label=positive, pred=negative: "코 옆에 바를 때마다 살짝 따가워요" → 전반 긍정이나 따가움 언급으로 negative 분류. 경계 케이스.
- rating=3, label=neutral, pred=negative: "어떤 앰플을 쓰든 다 밀림;;;;" → neutral 라벨이지만 불만 내용. BiLSTM negative가 더 적절.

### 수정한 규칙

- skin_concern_codes 필터 버그 수정: parquet 재로드 시 list → numpy.ndarray 변환으로 isinstance(x, list) 실패.
  `_arr_nonempty()` 헬퍼로 대응. 수정 후 skin_concern_code_samples 20개 정상 생성, top_codes 집계도 정상.

### 아직 남은 위험

- C09/C10/C11/C12/C13 코드 의미 미확인 → UI에서 직접 노출 금지
- neutral_recall 0.586: neutral 리뷰가 negative/positive로 오분류 비율 높음
- coupang 전체 base_skin_type 없음 → Step 3 집계에서 coupang 전체 제외
- rating=4-5이면서 pred=negative인 케이스 존재 (불만족이지만 별점 높게 준 사례)

- Step 3 진행 가능 여부: **가능**
  - has_base_skin_type=True 189,665건 / product_key 2,221개 확인
  - base_skin_type + predicted_sentiment 결합 정상

### negative 샘플 판단

- 실제 부정처럼 보이는 샘플이 대부분인지: **예** — 20개 중 16개(80%) 명확한 부정. "트러블", "뒤집어짐", "간지러움", "재구매 안함", "최악" 등 전형적 표현 확인.
- 애매한 샘플 예시:
  - rating=4/label=positive/pred=negative: "자극없는데 눈에 따가워요, 다이소 토너 사서 쓸듯" — 텍스트 실질 불만, BiLSTM이 더 정확.
  - rating=5/label=positive/pred=negative: "코 옆에 살짝 따가워요" — 경계 케이스. negative 판정은 과도하지만 서비스 목적상 포함해도 무방.
- 주의할 점: negative 탐색 서비스 목적상 label=positive + pred=negative 케이스도 실제 유용함. predicted_sentiment 기반 필터링이 텍스트 실질 내용에 더 부합.

### mismatch 샘플 판단

- 별점/약한 라벨과 모델 예측이 달라진 이유로 보이는 것:
  1. label=positive / pred=neutral: 별점 4-5점이지만 "모르겠어요", "아직은 잘 모르겠고" 등 불확실 표현 → BiLSTM이 neutral로 적절 판정
  2. label=negative / pred=neutral: 별점 1-2점이지만 "가성비는 좋은데 세정력이 별로" 처럼 장단점 혼재 → 약한 라벨이 지나치게 negative, BiLSTM이 neutral로 합리적 판정
  3. label=positive / pred=negative: "이럴거면 다른거살게융", "다이소 사서 쓸듯" → 텍스트 실질 불만, BiLSTM이 더 정확
  4. label=neutral / pred=positive: 별점 3점이지만 "자극 없이, 촉촉함 유지, 피부결 정돈" 등 긍정 표현 나열 → BiLSTM positive 판정이 더 적절
- 서비스에서 predicted_sentiment를 우선 써도 되는지: **우선 사용 권장**. 약한 라벨(별점+규칙 기반)보다 BiLSTM이 텍스트 뉘앙스를 더 정확히 포착. 다만 neutral_recall 0.586이므로 neutral 예측 신뢰도 낮음 — Step 3 집계 시 neutral 분리 유지 필요.