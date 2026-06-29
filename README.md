# 화장품 리뷰 기반 피부타입 맞춤 부정 신호 리뷰 확인 서비스

> 기말 프로젝트 — 화장품 리뷰 크롤링 → 전처리 → 감성 분석 모델 학습 → Streamlit 배포

---

## 프로젝트 개요

화장품 플랫폼의 평균 별점은 "일반적으로 좋다"는 신호다. 그런데 화장품은 피부타입에 따라 반응이 다르다. 건성 피부에 좋은 제품이 지성 피부에는 트러블을 일으킬 수 있다.

이 프로젝트는 같은 피부타입 리뷰에서 감성 분석 모델이 부정으로 감지한 리뷰 비율을 기준으로 상품을 평가하는 서비스를 구현한다.

**데이터 파이프라인**:
```
크롤링 → 전처리 → 라벨링 → 모델 학습 → 모델 평가 → 추론 → Streamlit 배포
```

---

## 이 문서를 처음 보는 사람에게

| 보고 싶은 것 | 파일 |
|---|---|
| 프로젝트 전체 요약과 실행 방법 | 이 README.md |
| 크롤링, 전처리, 모델 학습 상세 | `docs/technical_report.md` |
| 개발 중 판단 흐름과 결정 근거 | `docs/development_journal.md` |
| 모델 평가 지표와 수동 검수 샘플 | `reports/` |
| 최종 서비스 실행 파일 | `streamlit_app_v2.py` |

---

## 전체 파이프라인

```
[크롤링]
  OliveYoung: Selenium(헤드풀) + requests(모바일 API 커서 페이지네이션)
  Musinsa/Coupang: 외부 CSV → normalize_external.py 변환
        ↓
[전처리]
  결측치·중복 제거 → 컬럼 통일 → 텍스트 정제
  별점 후보 라벨 × 4계층 키워드 → sentiment_label / ambiguous 분리
  Okt 형태소 분석(stem=True) → tokens_str
  stratified 8:2 split → train.parquet / val.parquet
        ↓
[모델 학습]
  Baseline: TF-IDF + LogisticRegression
  BiLSTM: TextVectorization → Embedding → BiLSTM → Dense
  Transformer: klue/bert-base fine-tuning
        ↓
[모델 평가]
  metrics.json / classification_report.csv / confusion_matrix.csv / history.csv
  수동 검수: 오분류 샘플 직접 확인 (181건)
        ↓
[추론 / 서비스 데이터 생성]
  precompute_preds.py → lstm_v3_preds.parquet
  build_service_reviews.py → service_reviews.parquet
  build_product_skin_aggregates.py → product_skin_aggregates.parquet
  build_recommendation_scores.py → product_recommendation_scores.parquet
        ↓
[Streamlit 배포]
  streamlit_app_v2.py (5개 탭)
```

---

## 크롤링 설계

### OliveYoung — Selenium + requests 혼용

OliveYoung은 상품 목록/상세 페이지가 JavaScript로 렌더링된다. 리뷰 데이터는 모바일 API 엔드포인트에서 JSON으로 제공된다.

| 역할 | 도구 | 이유 |
|---|---|---|
| 판매랭킹·상품 페이지 로딩 | Selenium (Chrome, headless=False) | JS 렌더링 필요 |
| 리뷰 수집 | requests (모바일 API) | JSON 직접 응답, 속도 우위 |

headless=True 모드는 OliveYoung이 봇으로 감지해 차단한다. 실제 Chrome 창이 뜨는 헤드풀 모드에서만 정상 동작한다.

### 커서 기반 페이지네이션

리뷰 API는 `page` 파라미터가 있지만 무시된다. 커서 방식으로만 동작한다.

- **엔드포인트**: `POST https://m.oliveyoung.co.kr/review/api/v2/reviews/cursor`
- 응답의 `nextCursorId / nextCursorScore / nextCursorCount` → 다음 요청의 `cursorId / cursorScore / cursorCount`
- 필수 헤더: `Origin: https://www.oliveyoung.co.kr`, `Referer: https://www.oliveyoung.co.kr/`
- `hasNext=false`가 될 때까지 반복

### 수집 대상 및 기준

| 카테고리 | 필터 코드 | 원본 리뷰 수 | product_id 수 |
|---|---:|---:|---:|
| skincare | 10000010001 | 73,194건 | 241개 |
| maskpack | 10000010009 | 58,906건 | 227개 |
| cleansing | 10000010010 | 51,955건 | 194개 |
| suncare | 10000010011 | 42,639건 | 176개 |
| 전체 | - | 226,694건 | 838개 |

위 수치는 최종 정리된 OliveYoung 원본 JSONL 기준이다. GitHub Release의 `oliveyoung_raw_data_v3.tar.gz`를 프로젝트 루트에서 압축 해제하면 `output/` 폴더가 복원된다.

### rate limit 처리

약 70개 상품(~2.5시간) 수집 후 HTTP 429 발생 → 즉시 중단. 재실행하면 완료된 상품을 건너뛰고 이어서 수집한다.

### Musinsa / Coupang 외부 데이터

외부 CSV를 `normalize_external.py`로 공통 스키마로 변환했다.

| 플랫폼 | 날짜 형식 변환 | review_id | skin_type 커버리지 |
|---|---|---|---|
| Musinsa | '26.05.04' → '2026-05-04' | SHA256 해시 | 62.9% |
| Coupang | Excel 일련번호 → datetime | SHA256 해시 | **0.0%** |

Coupang은 skin_type 컬럼이 없어서 피부타입 기반 집계에서 전체 제외됐다.

---

## 원본 데이터 구조와 플랫폼별 차이

### OliveYoung JSONL 스키마 (각 줄이 리뷰 1건)

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

### 플랫폼별 skin_type 커버리지

아래 표는 `service_reviews.parquet` 기준의 전처리 후 서비스 데이터 현황이다. OliveYoung 원본 JSONL(226,694건)과 전처리 후 서비스 데이터(172,109건)는 다른 기준이다.

| 플랫폼 | 전체 리뷰 | base_skin_type 있음 | 피부타입 추천 사용 |
|---|---|---|---|
| OliveYoung | 172,109 | 39.3% | O |
| Musinsa | 194,144 | 62.9% | O |
| **Coupang** | 36,185 | **0.0%** | **X** |
| **전체** | **402,438** | **47.1%** | - |

skin_concern은 OliveYoung에만 존재 (전체의 17.3%).

---

## 전처리 설계

### 처리 흐름

| 단계 | 처리 내용 | 코드 |
|---|---|---|
| 결측치·중복 제거 | review_text 결측, review_id 중복 제거 | `preprocess/cleaning.py` |
| 컬럼 통일 | 플랫폼별 → ReviewSchema 공통 스키마 | `normalize_external.py`, `preprocess/io.py` |
| 텍스트 정제 | HTML·특수문자 제거 → `clean_review` | `preprocess/cleaning.py` |
| 형태소 분석 | Okt(stem=True) + 불용어 제거 → `tokens_str` | `preprocess/tokenize.py` |
| 라벨링 | 별점 후보 × 4계층 키워드 → sentiment_label / ambiguous | `preprocess/labeling.py` |
| 정규화 | skin_type → `base_skin_type` 5종 추출 | `recommendation/normalization.py` |
| 분리 | stratified 8:2 → train / val | `preprocess/split.py` |

### 클래스 분포

| 클래스 | 건수 | 비율 |
|---|---|---|
| positive | ~352K | 87.5% |
| negative | ~37K | 9.3% |
| neutral | ~13K | 3.2% |

모든 모델에 `class_weight=balanced`를 적용했다.

---

## 라벨링 기준과 한계

### 약한 라벨(Weak Label) 방식

정답 라벨이 없어서 별점과 텍스트 규칙을 교차하는 방식을 사용했다.

1. **별점 기반 후보 라벨**: ★4~5 → positive, ★1~2 → negative, ★3 → neutral
2. **4계층 키워드 교차 검증**:

| 계층 | 역할 |
|---|---|
| NEGATIVE_ABSENCE_PATTERNS | "자극없이", "트러블없는" 등 부재 표현 보호 |
| NEGATIVE_ABSENCE_KEYWORDS | 부재 키워드 보호 |
| NEGATIVE_CONTEXT_EXCEPTIONS | "최악이었는데 좋아졌어요" 같은 긍정 맥락 처리 |
| NEGATIVE_KEYWORDS / POSITIVE_KEYWORDS | 최종 감성 판단 |

3. **결과**: 일치 → `sentiment_label` 확정 / 불일치 → `ambiguous` 분리 (전체의 22.5%)

### 키워드 확장 (17개 → 55개)

한국어에서 조사 변형("효과 없" vs "효과가 없", "효과는 없")이 전혀 다른 문자열이 된다는 문제를 실측으로 확인했다. 865건의 미포착 케이스를 분석한 뒤 NEGATIVE_KEYWORDS를 55개로 확장했다.

### ★1~2+mixed → negative 복구

별점 ★1~2이면서 텍스트 규칙이 긍정인 케이스 6,475건을 직접 50건 검수한 결과, 48/50건이 부정 리뷰였다. 이 케이스를 `negative`로 복구했다.

---

## 모델 학습

### Baseline (TF-IDF + LogisticRegression)

```bash
python train_baseline.py --class-weight balanced
```

| 파라미터 | 값 |
|---|---|
| vectorizer | TF-IDF (n-gram 1~2) |
| class_weight | balanced |
| 입력 | tokens_str |

### BiLSTM

```bash
# 스모킹 테스트 먼저
python train_lstm.py --class-weight balanced --sample 5000 --epochs 1

# 전체 학습
python train_lstm.py --class-weight balanced
```

| 파라미터 | 값 | 이유 |
|---|---|---|
| MAX_TOKENS | 80,000 | 한국어 형태소 어휘 범위 |
| SEQUENCE_LENGTH | 120 | 화장품 리뷰 평균 길이 고려 |
| EMBEDDING_DIM | 128 | 경량+성능 균형 |
| LSTM_UNITS | 64 | 과적합 방지 |
| DROPOUT_RATE | 0.4 | 정규화 |
| BATCH_SIZE | 256 | GPU 메모리 한계 내 최대 |
| EPOCHS | 10 (EarlyStopping patience=2) | |
| class_weight | balanced | |
| 입력 | tokens_str | |

### Transformer (KLUE-BERT)

```bash
# 스모킹 테스트 먼저 (필수 — 설정 오류 사전 확인)
python train_transformer.py --run-name transformer_final_v3 --epochs 1 --sample 5000

# 전체 학습
python train_transformer.py --run-name transformer_final_v3 --epochs 5
```

| 파라미터 | 값 | 이유 |
|---|---|---|
| model_name | klue/bert-base | 한국어 특화 사전학습 |
| MAX_LENGTH | 160 | 화장품 리뷰 길이 + 여유 |
| BATCH_SIZE | 16 | 메모리 제약 |
| EPOCHS | 5 (EarlyStopping) | |
| LEARNING_RATE | 2e-5 | BERT fine-tuning 표준 |
| WEIGHT_DECAY | 0.01 | L2 정규화 |
| class_weight | balanced | |
| fp16 | False | Windows GPU 환경 불안정 |
| dataloader_num_workers | 0 | Windows 멀티프로세스 데드락 방지 |
| 입력 | clean_review (원문) | AutoTokenizer 직접 처리 |

---

## 모델 성능 비교

| 모델 | accuracy | macro_f1 | neg_recall | neu_recall | pos_recall |
|---|---|---|---|---|---|
| Baseline (none) | 0.9514 | 0.6250 | 0.7996 | 0.0271 | 0.9939 |
| Baseline (balanced) | 0.9067 | 0.6692 | 0.8098 | 0.4410 | 0.9339 |
| LSTM v1 | 0.880 | 0.661 | 0.742 | 0.242 | — |
| LSTM v2 | 0.906 | 0.628 | 0.819 | 0.589 | — |
| **LSTM v3** | **0.893** | **0.666** | **0.732** | **0.586** | **0.921** |
| Transformer v1 | 0.979 | 0.728 | 0.895 | 0.252 | — |
| Transformer v2 | 0.964 | 0.788 | 0.871 | 0.475 | 0.991 |
| **Transformer v3** | **0.964** | **0.788** | **0.871** | **0.475** | **0.991** |

v1→v2→v3 반복 개선 이유:
- v1→v2: 외부 데이터 추가, 라벨링 개선 → neutral_recall 2배 향상
- v2→v3: 키워드 17→55개 확장, ★1~2 복구

자세한 내용: `docs/technical_report.md`

---

## 오분류 분석

### neutral 과예측 문제

LSTM v3 neutral_precision=0.196. class_weight=balanced 적용으로 neutral recall이 0.242→0.586으로 개선됐지만, neutral precision이 낮아지는 trade-off가 있다.

부정 신호 탐지 목적에서는 이 trade-off를 수용했다.

### 수동 검수에서 확인한 오분류

`reports/service_reviews_manual_review_samples.md` (181건 직접 확인):

| 별점 | 약한 라벨 | LSTM | 실제 내용 |
|---|---|---|---|
| ★4 | positive | **negative** | "눈에 따가워요, 다이소 토너 쓸 것 같아요" |
| ★5 | positive | **negative** | "코 옆에 살짝 따가워요" |

별점 기반 약한 라벨보다 LSTM 예측이 더 정확한 케이스가 있었다.

---

## 추천 점수 산식

```
recommendation_score = skin_component + overall_component - caution_penalty

skin_component (0~65)   = (1 - skin_negative_rate) × evidence_weight × 65
overall_component (0~35) = (avg_rating/5)×20 + positive_rate×10 + (1-neg_rate)×5
caution_penalty          = 부정 신호 높음 → 20 / 중간 → 10 / 기타 → 0
```

**evidence_weight**: 해당 피부타입 리뷰 건수에 따라 다름

| 수준 | 조건 | 가중치 |
|---|---|---|
| strong | ≥ 20건 | 1.0 |
| limited | ≥ 5건 | 0.7 |
| insufficient | < 5건 | 0.3 |

집계 결과: 6,008행, 1,521개 상품, 평균 점수 70.56

---

## 서비스 구조 (Streamlit 5개 탭)

**파일**: `streamlit_app_v2.py`

| 탭 | 이름 | 주요 기능 |
|---|---|---|
| tab_skin | 피부타입 맞춤 추천 | 피부타입별 추천 점수 상위 상품 |
| tab1 | 일반 상품 추천 | 부정 신호 비율 기반 상품 리스트 |
| tab2 | 상품 비교 | 상품 2개 병렬 부정 신호 비교 |
| tab3 | 모델·데이터 리포트 | 학습 지표, 혼동 행렬, 하이퍼파라미터 |
| tab4 | 리뷰 직접 분석 | 3개 모델 실시간 추론 |

사이드바: platform → category → brand cascade 필터 (상위 선택 변경 시 하위 자동 초기화)

---

## 프로젝트 디렉터리 구조

```
oliveyoung_crawler/
├── README.md
├── requirements.txt
├── .gitignore
│
├── main.py                          # 크롤러 진입점
├── normalize_external.py            # Musinsa/Coupang CSV → 공통 스키마
├── run_preprocess.py                # 전처리 파이프라인 진입점
├── train_baseline.py                # TF-IDF + LogReg 학습
├── train_lstm.py                    # BiLSTM 학습
├── train_transformer.py             # KLUE-BERT 학습
├── precompute_preds.py              # BiLSTM 사전 추론
├── precompute_transformer.py        # Transformer 사전 추론
├── streamlit_app_v2.py              # Streamlit 앱 (최종)
│
├── oliveyoung/                      # 크롤러 패키지
│   ├── crawlers/ (category, product, review)
│   └── pipeline.py / config.py / schema.py / browser.py / storage.py
│
├── preprocess/                      # 전처리 패키지
│   ├── cleaning.py / labeling.py / tokenize.py / split.py / config.py / io.py
│   └── stopwords.txt
│
├── sentiment/                       # 학습 유틸
│   └── data.py / metrics.py
│
├── recommendation/                  # 추천 점수 모듈
│   └── normalization.py / aggregation.py / scoring.py
│
├── scripts/                         # 서비스 데이터 빌드
│   └── build_service_reviews.py / build_product_skin_aggregates.py / build_recommendation_scores.py / check_normalization.py
│
├── preprocessed_v3/                 # 전처리 산출물
│   ├── product_recommendation_scores.parquet  (0.37MB, Git 포함)
│   ├── product_skin_aggregates.parquet        (0.32MB, Git 포함)
│   ├── lstm_v3_preds.parquet                  (4.6MB, Git 포함)
│   ├── transformer_v3_preds.parquet           (4.6MB, Git 포함)
│   ├── service_reviews.parquet                (106MB, Releases)
│   ├── train.parquet                          (119.8MB, Releases)
│   └── val.parquet                            (30.3MB, Releases)
│
├── models/
│   ├── README.md
│   ├── lstm_final_v3_vocab.txt                (458KB, Git 포함)
│   ├── transformer_final_v3/                  (config/tokenizer, Git 포함)
│   ├── lstm_final_v3.keras                    (119MB, Releases)
│   ├── tfidf_vectorizer.joblib                (4.3MB, Releases)
│   └── baseline_logreg_balanced.joblib        (2.3MB, Releases)
│
├── data/
│   ├── raw/README.md                          # OliveYoung 원본 데이터 설명
│   ├── external/README.md                     # 외부 CSV 구조/변환 방법
│   └── processed/README.md                    # 전처리 데이터 설명
│
├── reports/                         # 모델 평가 결과
│   └── *_metrics.json / *_classification_report.csv / *_confusion_matrix.csv / *_history.csv / *_manual_review_samples.md
│
└── docs/
    ├── technical_report.md          # 크롤링~배포 상세 기술 보고서
    ├── development_journal.md       # 개발 과정 실제 판단 흐름
    ├── service_design.md            # 서비스 설계 및 데이터 연결 구조
    ├── setup_verification.md        # 설치 및 실행 검증 가이드
    ├── adr/ADR-0001-*.md            # 라벨링 설계 ADR
    └── worklog/                     # 날짜별 개발 기록
```

---

## 실행 환경

- Python 3.11 (conda env `oliveyoung`)
- 운영체제: Windows 11 (Transformer 학습 시 Linux/WSL 권장)
- GPU: NVIDIA GPU 권장 (Transformer 학습 시)
- Chrome: 최신 버전 (OliveYoung 크롤링 시)

---

## 설치 방법

```bash
conda create -n oliveyoung python=3.11
conda activate oliveyoung
pip install -r requirements.txt
```

KoNLPy (선택 — 탭4 분석 정밀도 향상):

```bash
java -version    # Java 8 이상 필요
pip install konlpy
```

---

## 데이터 및 모델 준비 (3가지 모드)

### 모드 A — 최소 실행 (git clone만으로 완성)

별도 다운로드 없이 바로 실행 가능. 피부타입 추천 탭만 동작.

```bash
streamlit run streamlit_app_v2.py
```

### 모드 B — 표준 실행

**[GitHub Releases v1.0.0](https://github.com/gusn9719/WebCrawling/releases/tag/v1.0.0)** 에서 다운로드 후 아래 경로에 배치:

| 파일 | 배치 경로 |
|---|---|
| `service_reviews.parquet` | `preprocessed_v3/service_reviews.parquet` |
| `tfidf_vectorizer.joblib` | `models/tfidf_vectorizer.joblib` |
| `baseline_logreg_balanced.joblib` | `models/baseline_logreg_balanced.joblib` |
| `lstm_final_v3.keras` | `models/lstm_final_v3.keras` |

```bash
streamlit run streamlit_app_v2.py
```

### 모드 C — 전체 재현 (크롤링~배포)

```bash
# 1. OliveYoung 크롤링
python main.py --category all --max-products 100

# 2. 외부 데이터 변환 (원본 CSV 있을 경우)
python normalize_external.py

# 3. 전처리
python run_preprocess.py --include-external --output preprocessed_v3

# 4. 모델 학습
python train_baseline.py --class-weight balanced
python train_lstm.py --class-weight balanced
python train_transformer.py --run-name transformer_final_v3 --epochs 5

# 5. 서비스 데이터 생성
python precompute_preds.py
python scripts/build_service_reviews.py
python scripts/build_product_skin_aggregates.py
python scripts/build_recommendation_scores.py

# 6. Streamlit 실행
streamlit run streamlit_app_v2.py
```

자세한 내용: `docs/setup_verification.md`

---

## GitHub Releases 파일 목록

**Release**: https://github.com/gusn9719/WebCrawling/releases/tag/v1.0.0

| 파일 | 크기 | 배치 경로 | 설명 | 다운로드 |
|---|---|---|---|---|
| `oliveyoung_raw_data_v3.tar.gz` | 35.9MB | 프로젝트 루트에서 압축 해제하면 `output/` 폴더가 복원됨 | 최종 OliveYoung 원본 JSONL 226,694건 (4개 카테고리) | [다운로드](https://github.com/gusn9719/WebCrawling/releases/download/v1.0.0/oliveyoung_raw_data_v3.tar.gz) |
| `service_reviews.parquet` | 106MB | `preprocessed_v3/service_reviews.parquet` | 서비스 실행 필수 | [다운로드](https://github.com/gusn9719/WebCrawling/releases/download/v1.0.0/service_reviews.parquet) |
| `train.parquet` | 119.8MB | `preprocessed_v3/train.parquet` | 모델 학습 재현용 | [다운로드](https://github.com/gusn9719/WebCrawling/releases/download/v1.0.0/train.parquet) |
| `val.parquet` | 30.3MB | `preprocessed_v3/val.parquet` | 모델 평가 재현용 | [다운로드](https://github.com/gusn9719/WebCrawling/releases/download/v1.0.0/val.parquet) |
| `lstm_final_v3.keras` | 119MB | `models/lstm_final_v3.keras` | BiLSTM v3 모델 | [다운로드](https://github.com/gusn9719/WebCrawling/releases/download/v1.0.0/lstm_final_v3.keras) |
| `tfidf_vectorizer.joblib` | 4.3MB | `models/tfidf_vectorizer.joblib` | Baseline TF-IDF | [다운로드](https://github.com/gusn9719/WebCrawling/releases/download/v1.0.0/tfidf_vectorizer.joblib) |
| `baseline_logreg_balanced.joblib` | 2.3MB | `models/baseline_logreg_balanced.joblib` | Baseline LogReg | [다운로드](https://github.com/gusn9719/WebCrawling/releases/download/v1.0.0/baseline_logreg_balanced.joblib) |
| `model.safetensors` | 422MB | `models/transformer_final_v3/model.safetensors` | KLUE-BERT fine-tuned | [다운로드](https://github.com/gusn9719/WebCrawling/releases/download/v1.0.0/model.safetensors) |

---

## 주요 산출물

| 파일 | 역할 |
|---|---|
| `output/*.jsonl` | 최종 OliveYoung 원본 JSONL 226,694건 (Git 미포함, Releases 제공) |
| `preprocessed_v3/product_recommendation_scores.parquet` | 피부타입별 추천 점수 (6,008행) |
| `preprocessed_v3/product_skin_aggregates.parquet` | 피부타입별 부정 신호 집계 |
| `preprocessed_v3/lstm_v3_preds.parquet` | BiLSTM v3 전체 예측 캐시 |
| `reports/lstm_final_v3_metrics.json` | BiLSTM v3 평가 지표 |
| `reports/transformer_final_v3_metrics.json` | Transformer v3 평가 지표 |
| `reports/service_reviews_manual_review_samples.md` | 수동 검수 181건 |
| `docs/technical_report.md` | 기술 보고서 (크롤링~배포) |

---

## 사용 주의사항

1. **모델 예측은 참고용이다.** 이 서비스의 모든 예측은 약한 라벨(별점+텍스트 규칙)로 학습된 모델의 결과다. 사람이 직접 검수한 정답 라벨이 아니다.

2. **"모델 부정 감지 리뷰"와 "실제 부정 리뷰"는 다를 수 있다.** LSTM v3 neutral_precision=0.196으로, neutral로 예측된 리뷰 중 상당수가 실제로 neutral이 아닐 수 있다.

3. **Coupang 피부타입 추천 불가.** Coupang 데이터에 skin_type 정보가 없어서 피부타입 맞춤 추천 탭(tab_skin)에서 Coupang 데이터가 제외된다.

4. **전체 리뷰의 52.9%는 피부타입 정보가 없다.** base_skin_type 커버리지가 47.1%이므로, 피부타입 집계는 전체 데이터의 절반 미만을 기반으로 한다.

5. **OliveYoung 크롤링은 headless 불가.** Chrome 창이 실제로 열린다. 자동화 환경(CI/CD, headless 서버)에서는 크롤링이 동작하지 않는다.
