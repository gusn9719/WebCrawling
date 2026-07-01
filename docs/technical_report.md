# 기술 보고서 — 화장품 리뷰 기반 피부타입 맞춤 부정 신호 리뷰 확인 서비스

> 작성 기준일: 2026-06-29  
> 보고서 범위: 크롤링 → 전처리 → 라벨링 → 모델 학습 → 모델 평가 → 추론 → 배포

---

## 1. 전체 기술 파이프라인

```
[크롤링]
  OliveYoung (Selenium + requests, 커서 API)
  Musinsa / Coupang (외부 CSV → normalize_external.py)
       ↓
[전처리]
  결측치/중복 제거 → 컬럼 통일 → 텍스트 정제
  별점 기반 후보 라벨 → 4계층 키워드 교차 → sentiment_label / ambiguous 분리
  Okt 형태소 분석 → tokens_str
  stratified 8:2 split → train.parquet / val.parquet
       ↓
[모델 학습]
  Baseline: TF-IDF + LogisticRegression
  BiLSTM: TextVectorization → Embedding → BiLSTM → Dense
  Transformer: klue/bert-base (AutoModelForSequenceClassification)
       ↓
[모델 평가]
  metrics.json / classification_report.csv / confusion_matrix.csv / history.csv
  수동 검수: 오분류 샘플 직접 확인
       ↓
[추론 / 서비스 데이터 생성]
  precompute_preds.py → lstm_v3_preds.parquet
  scripts/build_service_reviews.py → service_reviews.parquet
  scripts/build_product_skin_aggregates.py → product_skin_aggregates.parquet
  scripts/build_recommendation_scores.py → product_recommendation_scores.parquet
       ↓
[Streamlit 배포]
  streamlit_app.py (5개 탭)
```

---

## 2. 크롤링 설계

### 2-1. OliveYoung — Selenium + requests 혼용

OliveYoung은 상품 목록/상세 페이지가 JavaScript로 렌더링되어 단순 HTTP 요청으로는 내용을 가져올 수 없다. 반면 리뷰 데이터는 모바일 API 엔드포인트를 통해 JSON 형태로 제공된다.

이 두 가지 특성 때문에 Selenium과 requests를 역할에 따라 분리했다.

| 역할 | 도구 | 이유 |
|---|---|---|
| 판매랭킹 페이지 로딩, 상품 URL 수집 | Selenium (헤드풀) | JS 렌더링 필요 |
| 상품 상세 페이지 로딩 | Selenium (헤드풀) | JS 렌더링 필요 |
| 리뷰 데이터 수집 | requests (모바일 API) | JSON 직접 응답, 속도 우위 |

headless=True 모드는 OliveYoung이 봇으로 감지해 차단하므로 실제 브라우저 창이 뜨는 헤드풀 모드로만 동작한다.

### 2-2. 커서 기반 페이지네이션

리뷰 API는 `page` 파라미터가 있지만 실제로는 무시된다. 커서 방식으로만 동작한다.

- **엔드포인트**: `POST https://m.oliveyoung.co.kr/review/api/v2/reviews/cursor`
- **필수 헤더**: `Origin: https://www.oliveyoung.co.kr`, `Referer: https://www.oliveyoung.co.kr/`
- **커서 체인**: 응답의 `nextCursorId / nextCursorScore / nextCursorCount` → 다음 요청의 `cursorId / cursorScore / cursorCount`
- 응답에 `hasNext=false`가 될 때까지 반복

### 2-3. 상품 선정 기준

판매랭킹 URL을 사용하며, 카테고리별 상위 100개 상품을 한 번에 반환한다 (페이지네이션 불필요).

| 카테고리 | 필터 코드 |
|---|---|
| skincare | 10000010001 |
| maskpack | 10000010009 |
| cleansing | 10000010010 |
| suncare | 10000010011 |

상품 선정 전 리뷰 수를 먼저 조회한다 (review stats API). **MIN_REVIEW_COUNT=100** 미만 상품은 제외 (품질 게이트).

### 2-4. rate limit 처리

약 70개 상품(~2.5시간) 수집 후 HTTP 429가 발생한다. 재시도는 무의미하므로 `RateLimitError`로 즉시 중단한다. 재실행하면 완료된 상품을 건너뛰고 이어서 수집한다.

**이어받기 구현** (`storage.py`):
- `output/{category}_reviews.jsonl`에 리뷰를 append 방식으로 저장
- `seen_ids` 집합으로 review_id 중복 방지
- 상품 전체 리뷰가 저장 완료되면 `is_product_done(product_id)` 체크로 다음 실행 시 skip

### 2-5. 외부 데이터 — Musinsa / Coupang

Musinsa와 Coupang 데이터는 외부 CSV 파일을 공통 스키마로 변환하는 방식으로 통합했다 (`normalize_external.py`).

| 항목 | Musinsa | Coupang |
|---|---|---|
| 날짜 형식 | '26.05.04' → '2026-05-04' | Excel 일련번호 → datetime |
| review_id | SHA256 해시 생성 | SHA256 해시 생성 |
| 부분 파일 | 단일 CSV | 4개 분할 파일 + 전체 파일 병합 |

---

## 3. 원본 데이터 구조와 플랫폼별 차이

### 3-1. OliveYoung 수집 스키마

`output/{category}_reviews.jsonl`의 각 줄 (JSON):

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
| skin_concern | str | 피부 고민 (null 가능) |
| raw_url | str | 상품 페이지 URL |
| review_id | str | 리뷰 고유 ID |

### 3-2. 플랫폼별 skin_type 커버리지

피부타입 추천 기능은 `skin_type` 데이터에 전적으로 의존한다. 플랫폼별 커버리지 차이가 서비스 범위를 결정했다.

| 플랫폼 | 전체 리뷰 수 | base_skin_type 있음 | 커버리지 |
|---|---|---|---|
| OliveYoung | ~270K | 39.3% | 중간 |
| Musinsa | ~100K | 62.9% | 높음 |
| Coupang | ~32K | **0.0%** | 없음 |
| 전체 | 402,438 | 47.1% | - |

**Coupang은 피부타입 필드 자체가 없어서 피부타입 기반 집계에서 전체 제외됐다.** OliveYoung과 Musinsa 데이터만 추천 점수 계산에 사용한다.

### 3-3. skin_concern 차이

`skin_concern` 컬럼은 OliveYoung에만 존재한다 (전체 리뷰의 17.3%). Musinsa/Coupang에는 없다.

---

## 4. 전처리 설계

### 4-1. 전처리 단계별 흐름

| 단계 | 파일 | 처리 내용 | 확인 근거 |
|---|---|---|---|
| 결측치 제거 | `preprocess/cleaning.py` | review_text 결측/빈 텍스트 제거 | 코드 직접 확인 |
| 중복 제거 | `preprocess/cleaning.py` | review_id 기준 중복 제거 | service_reviews_check.md: 중복 0건 |
| 컬럼 통일 | `normalize_external.py`, `preprocess/io.py` | 플랫폼별 → 공통 ReviewSchema | 코드 직접 확인 |
| 텍스트 정제 | `preprocess/cleaning.py` | HTML/특수문자 제거, 한글 중심 정제 → clean_review | 코드 확인 |
| 불용어 처리 | `preprocess/tokenize.py`, `stopwords.txt` | Okt(stem=True) 형태소 분석 + 불용어 제거 → tokens_str | 코드 확인 |
| 라벨링 | `preprocess/labeling.py`, `preprocess/config.py` | 별점 후보 + 4계층 키워드 교차 → sentiment_label / ambiguous | 코드+ADR-0001+worklog |
| 정규화 | `recommendation/normalization.py` | skin_type → base_skin_type 추출 | normalization_check.md |
| 분리 | `preprocess/split.py` | stratified 8:2 → train/val | run_preprocess.py |

### 4-2. skin_type 정규화

OliveYoung의 skin_type 원문은 "복합성 · 진정/보습" 같이 복합 정보가 합쳐진 형태다. 이를 파싱해서:
- `base_skin_type`: 건성 / 지성 / 복합성 / 민감성 / 중성 중 하나
- `skin_need_tags`: 진정, 보습 등 케어 니즈 리스트
- `skin_concern_tags`: skin_concern 컬럼 파싱 결과

base_skin_type 추출 성공률: 99.6%

### 4-3. 학습 데이터 구성

train/val 분리 후 클래스 분포:

| 클래스 | 건수 | 비율 |
|---|---|---|
| positive | ~352K | 87.5% |
| negative | ~37K | 9.3% |
| neutral | ~13K | 3.2% |
| 합계 | ~402K | 100% |

클래스 불균형이 심해서 모든 모델에 `class_weight=balanced`를 적용했다.

---

## 5. 라벨링 설계와 한계

### 5-1. 약한 라벨(Weak Label) 방식

사전에 정답 라벨이 없어서 별점과 텍스트 규칙을 교차하는 약한 라벨링 방식을 사용했다.

1. **별점 기반 후보 라벨**:
   - ★4~5 → positive 후보
   - ★1~2 → negative 후보
   - ★3 → neutral 후보

2. **텍스트 규칙 라벨** (`_text_rule_label()`): 4계층 키워드 검사

3. **교차 검증 결과**:
   - 일치 → `sentiment_label` 확정
   - 불일치 → `is_ambiguous=True` (학습에서 제외)

### 5-2. 4계층 키워드 설계

순서대로 적용한다.

| 계층 | 역할 | 예시 |
|---|---|---|
| NEGATIVE_ABSENCE_PATTERNS | 부재 표현 전체 보호 (정규식) | "자극없이", "트러블없는" |
| NEGATIVE_ABSENCE_KEYWORDS | 부재 표현 키워드 보호 | "자극없", "트러블없" |
| NEGATIVE_CONTEXT_EXCEPTIONS | 부정 키워드를 긍정 맥락에서 무력화 | "최악이었는데 좋아졌어요" |
| NEGATIVE_KEYWORDS / POSITIVE_KEYWORDS | 최종 감성 판단 | "환불", "재구매" |

이 4계층 설계가 필요한 이유는 한국어 특성에 있다. "자극 없이 순해요"는 긍정 리뷰이지만, 단순히 "자극"이나 "없"을 각각 탐지하면 오분류된다.

### 5-3. 키워드 확장 과정 (17개 → 55개)

초기 키워드 17개로는 조사 변형, 붙여쓰기, 한국어 어미 변형을 처리하지 못했다.

`edge_case_analysis.txt`에서 확인된 미포착 패턴:

| 패턴 | 미포착 건수 | 이유 |
|---|---|---|
| "효과(가/는/도) 없" | 865건 | 조사 포함 형태 미등록 |
| "흡수안됩" | 미확인 | 붙여쓰기 |
| "재구매안", "추천안" | 미확인 | 부정 결합어 |

이를 확인한 뒤 NEGATIVE_KEYWORDS를 55개로 확장했다 (worklog 2026-06-22).

### 5-4. ★1~2+mixed → negative 복구

ambiguous 분리 이후 "★1~2인데 텍스트 규칙이 긍정(mixed)"인 케이스 6,475건을 다시 검토했다.

50건을 직접 확인한 결과 48/50건이 명확한 부정 리뷰였다. "효과가 좋아요"를 긍정 키워드로 탐지했지만 전체 맥락이 불만족인 경우였다. 이 케이스를 `negative`로 복구하기로 결정했다 (labeling.py `_finalize_label()`).

### 5-5. ambiguous 분리

전체의 22.5%가 ambiguous로 분리되어 학습에서 제외됐다.

| 원인 | 예시 |
|---|---|
| ★4~5 + 부정 텍스트 | "별점 주기 아깝지만 써봤으니까 올려요" → 별점 4, 부정 텍스트 |
| ★1~2 + 긍정 텍스트 (별점 오기 의심) | ★1인데 "너무 좋아요" |
| ★3 + 강한 감성 텍스트 | ★3인데 "최악이에요" |

★4~5+mixed는 positive로 강제 분류하지 않았다. 클래스 불균형이 더 심해질 우려가 있었기 때문이다.

### 5-6. 라벨링 한계

1. 규칙 기반 라벨은 사람이 검수한 정답이 아니다 (약한 라벨).
2. neutral 클래스 정밀도가 매우 낮다 (LSTM v3: neutral_precision=0.196).
3. ★1~2+mixed 케이스의 약 4%는 별점 오기(불만족 상품에 실수로 높은 별점)로 판단하고 수용했다.
4. C09/C10/C11/C12/C13 피부고민 코드의 의미가 확인되지 않아 UI에 직접 노출하지 않았다.

---

## 6. 모델 학습

### 6-1. Baseline (TF-IDF + LogisticRegression)

**파일**: `train_baseline.py`

| 파라미터 | 값 | 이유 |
|---|---|---|
| vectorizer | TF-IDF (n-gram 1~2) | 한국어 형태소 기반 토큰 입력 |
| class_weight | balanced | 클래스 불균형 (positive 87.5%) |
| max_iter | 1000 | 수렴 보장 |

두 버전(none / balanced)을 비교해서 balanced가 neutral recall에서 우위를 보였다.

### 6-2. BiLSTM

**파일**: `train_lstm.py`

| 파라미터 | 값 | 이유 |
|---|---|---|
| MAX_TOKENS | 80,000 | 한국어 형태소 어휘 범위 커버 |
| SEQUENCE_LENGTH | 120 | 화장품 리뷰 평균 길이 고려 |
| EMBEDDING_DIM | 128 | 경량+성능 균형 |
| LSTM_UNITS | 64 | 과적합 방지 |
| DROPOUT_RATE | 0.4 | 정규화 |
| BATCH_SIZE | 256 | GPU 메모리 한계 내 최대 |
| EPOCHS | 10 (EarlyStopping) | EarlyStopping(patience=2)으로 실제로는 4~6 epoch |
| optimizer | adam | 기본값, 수렴 안정적 |
| loss | sparse_categorical_crossentropy | 다중 클래스 |
| class_weight | balanced | 클래스 불균형 |
| random_seed | 42 | 재현성 |

**BiLSTM 입력**: `tokens_str` (Okt 형태소 분석 후 공백 구분된 토큰 문자열)

**재학습 이력**:
- v1: OliveYoung 데이터만 (~75K), 단순 별점 라벨 → neutral_recall=0.242
- v2: 외부 데이터 추가 (~402K), 라벨링 개선 → neutral_recall=0.589 (2배 개선)
- v3: 키워드 17→55개, ★1~2 복구 → neutral_recall=0.586 (macro_f1=0.666)

### 6-3. Transformer (KLUE-BERT)

**파일**: `train_transformer.py`

| 파라미터 | 값 | 이유 |
|---|---|---|
| model_name | klue/bert-base | 한국어 특화 사전학습 모델 |
| MAX_LENGTH | 160 | 화장품 리뷰 길이 + 여유 |
| BATCH_SIZE | 16 | 메모리 제약 (Transformer 큰 모델) |
| EPOCHS | 5 (v3) / 3 (v2) | EarlyStoppingCallback(patience=2) |
| LEARNING_RATE | 2e-5 | BERT fine-tuning 표준값 |
| WEIGHT_DECAY | 0.01 | L2 정규화 |
| WARMUP_RATIO | 0.1 | 학습 초기 안정화 |
| class_weight | balanced | 클래스 불균형 (WeightedTrainer 사용) |
| fp16 | False | Windows GPU 환경 불안정 |
| dataloader_num_workers | 0 | Windows에서 멀티프로세스 데드락 방지 |
| seed | 42 | 재현성 |

**Transformer 입력**: `clean_review` (원문 직접 입력, AutoTokenizer가 토크나이징)

**재학습 이력**:
- v1: neutral_recall=0.252 → 심각한 neutral 무시
- v2: v3 데이터로 재학습 → neutral_recall=0.475 (2배 개선)
- v3: epochs=5 → 추가 학습, v2 대비 소폭 개선

### 6-4. 스모킹 테스트

전체 학습 전에 `--sample 5000 --epochs 1` 옵션으로 소규모 실행 가능성 검증을 먼저 했다. 특히 Transformer 학습은 설정 오류 시 수 시간을 낭비하므로 스모킹 테스트가 중요했다.

---

## 7. 모델 성능 비교

| 모델 | accuracy | macro_f1 | neg_recall | neu_recall | pos_recall |
|---|---|---|---|---|---|
| Baseline(none) | 0.9514 | 0.6250 | 0.7996 | 0.0271 | 0.9939 |
| Baseline(balanced) | 0.9067 | 0.6692 | 0.8098 | 0.4410 | 0.9339 |
| LSTM v1 | 0.880 | 0.661 | 0.742 | 0.242 | — |
| LSTM v2 | 0.906 | 0.628 | 0.819 | 0.589 | — |
| **LSTM v3** | **0.893** | **0.666** | **0.732** | **0.586** | **0.921** |
| Transformer v1 | 0.979 | 0.728 | 0.895 | 0.252 | — |
| Transformer v2 | 0.964 | 0.788 | 0.871 | 0.475 | 0.991 |
| **Transformer v3** | **0.964** | **0.788** | **0.871** | **0.475** | **0.991** |

**최종 선택**: BiLSTM v3 (서비스 기본), Transformer v3 (탭4 비교용), Baseline balanced (참조용)

---

## 8. 오분류 분석

### 8-1. neutral 과예측 문제

LSTM v3의 neutral_precision=0.196은 전체의 3.2%인 neutral 리뷰를 실제보다 3배 많이 예측함을 뜻한다. class_weight=balanced 적용으로 neutral recall은 개선됐지만 precision이 낮아졌다. 이 trade-off는 부정 신호 탐지 목적에서는 수용 가능한 수준으로 판단했다.

### 8-2. 수동 검수에서 확인한 오분류 사례

`service_reviews_manual_review_samples.md`에서 직접 확인한 사례:

| 별점 | 약한 라벨 | LSTM 예측 | 리뷰 원문 (요약) | 실제 판단 |
|---|---|---|---|---|
| ★4 | positive | **negative** | "자극없는데 눈에 따가워요, 다이소 토너 쓸듯" | LSTM이 더 정확 |
| ★5 | positive | **negative** | "코 옆에 살짝 따가워요" | 경계 케이스 |
| ★3 | neutral | **negative** | "어떤 앰플이든 밀림;;;;" | LSTM negative 적절 |
| ★4 | positive | **neutral** | "아직은 잘 모르겠고" | LSTM neutral 적절 |

별점 기반 약한 라벨보다 BiLSTM의 예측이 더 정확한 케이스가 확인됐다. 이는 약한 라벨의 한계를 보여준다.

### 8-3. edge case: "최악" 키워드

`edge_case_analysis.txt`에서 확인된 사례:

> "피부 컨디션이 최악이었는데 아누아 쓰고 좋아졌어요"

"최악"은 부정 키워드이지만 문맥상 긍정 리뷰다. NEGATIVE_CONTEXT_EXCEPTIONS로 이 패턴을 처리했다. 완전히 막을 수는 없지만 false positive 건수가 service에서 수용 가능한 수준이라 판단했다.

---

## 9. 모델 저장 방식

| 모델 | 저장 형식 | 파일 |
|---|---|---|
| Baseline vectorizer | joblib (scikit-learn) | `models/tfidf_vectorizer.joblib` |
| Baseline LogReg | joblib (scikit-learn) | `models/baseline_logreg_balanced.joblib` |
| BiLSTM | Keras SavedModel | `models/lstm_final_v3.keras` |
| BiLSTM 어휘 | txt (한 줄에 한 토큰) | `models/lstm_final_v3_vocab.txt` |
| Transformer | safetensors (Hugging Face) | `models/transformer_final_v3/model.safetensors` |
| Transformer tokenizer | JSON/txt 파일들 | `models/transformer_final_v3/` |

Transformer는 학습 중 EarlyStopping이 발동하면 `checkpoint-{step}/` 폴더에 저장된다. 최종 추론에는 이 체크포인트 전체가 필요하며, optimizer.pt(844MB)는 이후 재학습 때만 필요하다. 서비스 추론에는 `model.safetensors`와 tokenizer 파일만 있으면 된다.

---

## 10. 추천 점수 계산 방식

**파일**: `recommendation/scoring.py`

### 산식

```
recommendation_score = skin_component + overall_component - caution_penalty

skin_component (0~65)  = (1 - skin_negative_rate) × evidence_weight × 65
overall_component (0~35) = (avg_rating/5)×20 + positive_rate×10 + (1-neg_rate)×5
caution_penalty = high_negative_signal→20, moderate→10, else 0
```

### 근거 가중치 (evidence_weight)

증거가 많을수록 점수 신뢰도가 높아야 하므로 리뷰 건수에 따라 가중치를 다르게 적용했다.

| evidence_level | 조건 | 가중치 |
|---|---|---|
| strong_evidence | 해당 피부타입 리뷰 ≥ 20건 | 1.0 |
| limited_evidence | ≥ 5건 | 0.7 |
| insufficient_evidence | < 5건 | 0.3 |

### 집계 결과

- 6,008행, 1,521개 상품
- 플랫폼: OliveYoung 62.1%, Musinsa 37.9%, Coupang 0%
- 점수 분포: 평균 70.56, 표준편차 19.17, 범위 8.82~99.82

### 표시 티어

| 티어 | 의미 | 비율 |
|---|---|---|
| strong_candidate | 부정 신호 낮음, 강한 근거 | 30.4% |
| review_before_buying | 리뷰 확인 권장 | 29.5% |
| insufficient_evidence | 해당 피부타입 리뷰 부족 | 26.9% |
| caution_check | 주의 필요, 리뷰 확인 권장 | 8.6% |
| negative_review_first | 부정 신호 높음, 부정 리뷰 먼저 확인 | 4.6% |

---

## 11. 모델 추론 방식

### 11-1. 사전 예측 (precompute)

Streamlit에서 실시간으로 402K건 전체를 추론하면 속도가 너무 느리다. 전체 데이터에 대한 예측값을 미리 계산해 parquet 파일로 저장하는 방식을 채택했다.

```
precompute_preds.py → lstm_v3_preds.parquet (4.6MB)
precompute_transformer.py → transformer_v3_preds.parquet (4.6MB)
```

### 11-2. Streamlit 모델 로딩

```python
@st.cache_resource  # 세션 간 캐시 유지
def load_lstm_v3():
    model = tf.keras.models.load_model("models/lstm_final_v3.keras")
    vocab = load_vocab("models/lstm_final_v3_vocab.txt")
    return model, vocab
```

첫 로딩은 30~60초 소요된다. 이후 세션 내에서는 캐시를 사용한다.

### 11-3. KoNLPy 없을 때 fallback

탭4 실시간 분석에서 Okt 형태소 분석이 필요하다. KoNLPy/Java가 없는 환경에서는 한글 문자만 남기는 단순 필터로 fallback해서 오류 없이 동작한다.

### 11-4. Fallback — 사전 예측 파일이 없을 때

`lstm_v3_preds.parquet`가 없으면 탭1/2 집계 시 실시간 배치 추론으로 대체된다. 속도는 느리지만 기능은 유지된다.

---

## 12. Streamlit 앱 구조

**파일**: `streamlit_app.py`

### 5개 탭

| 탭 | 이름 | 주요 데이터 |
|---|---|---|
| tab_skin | 피부타입 맞춤 추천 | `product_recommendation_scores.parquet` |
| tab1 | 일반 상품 추천 | `service_reviews.parquet` + BiLSTM 예측 |
| tab2 | 상품 비교 | 상품 2개 병렬 |
| tab3 | 모델·데이터 리포트 | `reports/*.json`, `*.csv` |
| tab4 | 리뷰 직접 분석 | 3개 모델 실시간 추론 |

### 전역 필터

사이드바에서 platform → category → brand 순으로 cascade 필터가 적용된다. 상위 선택이 바뀌면 하위 선택이 자동으로 초기화된다.

---

## 13. GitHub 배포 구조

자세한 내용은 `docs/setup_verification.md` 참조.

- 직접 Git: 코드, 소용량 parquet, 문서
- GitHub Releases: 대용량 모델 파일, 학습/서비스 parquet, OliveYoung 원본 JSONL
- 제외: 중간 체크포인트, 이전 버전 모델, 복구본, 개발 임시 파일

---

## 14. 한계와 개선 방향

### 14-1. 현재 한계

1. **neutral 과예측**: LSTM v3 neutral_precision=0.196. 중립 리뷰 오분류가 많다.
2. **Coupang 피부타입 없음**: Coupang 데이터 전체가 피부타입 추천에서 제외된다.
3. **C09~C13 피부고민 코드**: 의미 미확인으로 UI 직접 노출을 하지 않는다.
4. **OliveYoung 크롤링 의존성**: headless 불가, 429 rate limit으로 장기 수집에 제약이 있다.
5. **Coupang 피부타입 데이터 없음**: skin_type 0%로 피부타입 기반 추천 불가.

### 14-2. 개선 방향

1. neutral 클래스에 특화된 추가 학습 데이터 구축 (인간 검수 라벨)
2. Coupang skin_type 데이터 대안 방법 탐색 (리뷰 텍스트에서 피부타입 추출 등)
3. 피부타입별 false positive rate 모니터링
4. 실제 사용자 피드백 기반 모델 성능 재평가
