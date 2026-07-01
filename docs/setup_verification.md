# 설치 및 실행 검증 가이드

---

## 실행 모드 선택

이 프로젝트는 필요한 파일 수에 따라 3가지 실행 모드로 나뉜다.

| 모드 | 추가 다운로드 | 실행 가능 기능 |
|---|---|---|
| **A (최소)** | 없음 (git clone만으로 완성) | 피부타입 추천 탭 |
| **B (표준)** | service_reviews + BiLSTM 모델 | 주요 탭 전체 |
| **C (전체 재현)** | 원본 데이터 + 전체 모델 + 학습 | 학습/추론 전체 파이프라인 |

---

## 공통 환경 설치

### 1. Python 환경

Python 3.11 기준. conda 사용을 권장한다.

```bash
conda create -n oliveyoung python=3.11
conda activate oliveyoung
pip install -r requirements.txt
```

### 2. KoNLPy (선택 — 탭4 분석 정밀도 향상)

KoNLPy는 Java에 의존한다. 탭4 실시간 분석에서 Okt 형태소 분석을 사용한다.  
미설치 시 한글 문자 필터링 fallback으로 동작한다 (기능 유지, 정밀도 제한).

```bash
# Java 8 이상 설치 확인
java -version

# KoNLPy 설치
pip install konlpy
```

### 3. Selenium (선택 — 크롤링 재실행 시)

OliveYoung 크롤링을 새로 실행하려면 Chrome과 Selenium이 필요하다.

```bash
pip install selenium undetected-chromedriver
```

---

## 모드 A — 최소 실행 (피부타입 추천 탭)

### 필요 파일

git clone 후 이미 포함된 파일:
- `preprocessed_v3/product_recommendation_scores.parquet` (0.37MB)
- `preprocessed_v3/product_skin_aggregates.parquet` (0.32MB)

추가 다운로드: **없음**

### 실행

```bash
conda activate oliveyoung
pip install -r requirements.txt
streamlit run streamlit_app.py
```

브라우저에서 `http://localhost:8501`을 열어 "피부타입 맞춤 추천" 탭이 정상 표시되면 완료.

### 예상 제한

| 탭 | 상태 | 이유 |
|---|---|---|
| 피부타입 맞춤 추천 (tab_skin) | 정상 | parquet 포함 |
| 일반 상품 추천 (tab1) | 데이터 없음 오류 | service_reviews.parquet 없음 |
| 상품 비교 (tab2) | 데이터 없음 오류 | service_reviews.parquet 없음 |
| 모델·데이터 리포트 (tab3) | 정상 | reports/ 포함 |
| 리뷰 직접 분석 (tab4) | 모델 없음 오류 | 모델 파일 없음 |

---

## 모드 B — 표준 실행 (주요 기능)

### 필요 파일 다운로드

GitHub Releases 페이지에서 아래 파일을 다운로드한다.

| 파일 | 크기 | 배치 경로 |
|---|---|---|
| `service_reviews.parquet` | 106MB | `preprocessed_v3/service_reviews.parquet` |
| `tfidf_vectorizer.joblib` | 4.3MB | `models/tfidf_vectorizer.joblib` |
| `baseline_logreg_balanced.joblib` | 2.3MB | `models/baseline_logreg_balanced.joblib` |
| `lstm_final_v3.keras` | 119MB | `models/lstm_final_v3.keras` |

`models/lstm_final_v3_vocab.txt`는 git에 포함되어 있으므로 별도 다운로드 불필요.

### 디렉터리 구조 확인

```
WebCrawling/
├── preprocessed_v3/
│   ├── product_recommendation_scores.parquet  ← git 포함
│   ├── product_skin_aggregates.parquet        ← git 포함
│   ├── lstm_v3_preds.parquet                  ← git 포함
│   ├── transformer_v3_preds.parquet           ← git 포함
│   └── service_reviews.parquet                ← Releases에서 다운로드 ★
├── models/
│   ├── lstm_final_v3_vocab.txt                ← git 포함
│   ├── tfidf_vectorizer.joblib                ← Releases에서 다운로드 ★
│   ├── baseline_logreg_balanced.joblib        ← Releases에서 다운로드 ★
│   └── lstm_final_v3.keras                    ← Releases에서 다운로드 ★
```

### 실행

```bash
conda activate oliveyoung
streamlit run streamlit_app.py
```

### 검증 체크리스트

- [ ] `http://localhost:8501` 접속 후 앱 로딩 완료
- [ ] 피부타입 맞춤 추천 탭: 상품 목록 표시
- [ ] 일반 상품 추천 탭: 필터 적용 후 상품 목록 표시
- [ ] 상품 비교 탭: 상품 2개 선택 후 비교 표시
- [ ] 모델·데이터 리포트 탭: 지표 수치 표시

---

## 모드 C — 전체 재현 (크롤링~배포)

### 1단계: 원본 데이터 준비

**OliveYoung 크롤링** (새로 수집하거나 Releases에서 다운로드):

```bash
# 새로 수집 (Chrome 브라우저 창이 자동으로 열린다, headless 불가)
python main.py --category all --max-products 100

# 또는 Releases에서 oliveyoung_raw_data_v3.tar.gz 다운로드 후 압축 해제
tar xzf oliveyoung_raw_data_v3.tar.gz
# → output/ 폴더에 *.jsonl 파일들이 생성됨
```

**크롤링 재실행 시 주의사항**:
- headless=True는 OliveYoung이 차단하므로 사용 불가
- 약 70개 상품(2.5시간) 후 rate limit(429) 발생 → 즉시 중단, 수 시간 후 재실행하면 이어서 수집
- `output/{category}_reviews.jsonl`에 이어서 저장됨 (중복 자동 제거)

**외부 데이터 변환** (Musinsa/Coupang CSV가 있을 경우):

```bash
python normalize_external.py
# → output_external/musinsa_reviews.jsonl, coupang_reviews.jsonl 생성
```

### 2단계: 전처리

```bash
# 외부 데이터 포함 전처리 (~2시간, KoNLPy Java 필요)
python run_preprocess.py --include-external --output preprocessed_v3
```

**전처리 주의사항**:
- KoNLPy 미설치 시 Okt 형태소 분석 단계에서 오류 발생 → 먼저 `java -version`으로 Java 설치 확인
- 전처리 중 중단 시 재실행하면 처음부터 다시 시작됨 (재개 불가)
- 완료 후 `preprocessed_v3/` 폴더에 train/val/service_reviews/ambiguous.parquet 생성

### 3단계: 모델 학습

**Baseline** (1~2분):

```bash
python train_baseline.py --class-weight balanced
```

**BiLSTM** (데이터 크기 기준 1~3시간, GPU 있으면 더 빠름):

```bash
# 스모킹 테스트 먼저 (권장)
python train_lstm.py --class-weight balanced --sample 5000 --epochs 1

# 전체 학습
python train_lstm.py --class-weight balanced
```

**Transformer KLUE-BERT** (GPU 권장, GPU 없으면 24시간+):

```bash
# 스모킹 테스트 먼저 (필수 — 설정 오류 사전 확인)
python train_transformer.py --run-name transformer_final_v3 --epochs 1 --sample 5000

# 전체 학습
python train_transformer.py --run-name transformer_final_v3 --epochs 5
```

**Transformer Windows 환경 설정**:
- `dataloader_num_workers=0` (기본값) — 변경하지 말 것 (멀티프로세스 데드락)
- `fp16=False` (기본값) — Windows GPU 환경에서 불안정

### 4단계: 서비스 데이터 생성

```bash
# BiLSTM 전체 데이터 사전 추론 (1~2시간)
python precompute_preds.py

# 서비스용 데이터 빌드
python scripts/build_service_reviews.py
python scripts/build_product_skin_aggregates.py
python scripts/build_recommendation_scores.py
```

### 5단계: Streamlit 실행

```bash
streamlit run streamlit_app.py
```

### 전체 재현 예상 소요 시간

| 단계 | 예상 소요 |
|---|---|
| OliveYoung 크롤링 (전체) | 8~12시간 (rate limit 포함) |
| 전처리 | 1~2시간 |
| Baseline 학습 | 5분 이내 |
| BiLSTM 학습 | 1~3시간 |
| Transformer 학습 | GPU 있음: 4~6시간 / 없음: 24시간+ |
| 사전 추론 | 1~2시간 |
| 서비스 데이터 빌드 | 10분 이내 |

---

## 자주 발생하는 오류

### streamlit_app.py 실행 시 "FileNotFoundError: service_reviews.parquet"

원인: 모드 A로 실행 시 service_reviews.parquet 없음  
해결: Releases에서 다운로드 후 `preprocessed_v3/service_reviews.parquet`로 배치 (모드 B)

### "ModuleNotFoundError: No module named 'konlpy'"

원인: KoNLPy 미설치  
해결: `pip install konlpy` 후 Java 설치 확인 (`java -version`)  
대안: 탭4 실시간 분석 시 fallback 모드로 동작 (기능 제한)

### Transformer 학습 중 "DataLoader worker exited unexpectedly"

원인: `dataloader_num_workers > 0` 설정  
해결: `train_transformer.py`에서 `dataloader_num_workers=0` 확인

### 크롤링 중 "RateLimitError: 429"

원인: OliveYoung rate limit  
해결: 프로그램이 자동 종료됨. 수 시간 후 같은 명령 재실행. 완료된 상품은 건너뛰고 이어서 수집

### "WebDriverException: chrome not reachable"

원인: Chrome 드라이버 버전 불일치  
해결: Chrome 버전 확인 후 `undetected-chromedriver` 재설치

---

## 검증 명령

```bash
# Python 환경 확인
python --version   # 3.11.x 이어야 함

# 핵심 라이브러리 버전 확인
python -c "import tensorflow as tf; print(tf.__version__)"
python -c "import transformers; print(transformers.__version__)"
python -c "import streamlit; print(streamlit.__version__)"

# 소용량 parquet 파일 확인 (모드 A 최소 파일)
python -c "import pandas as pd; df=pd.read_parquet('preprocessed_v3/product_recommendation_scores.parquet'); print(df.shape)"
# 예상 출력: (6008, ...)
```
