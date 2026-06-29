# data/processed — 전처리 완료 데이터

전처리 파이프라인(`run_preprocess.py`)의 산출물이다.  
대용량 파일은 GitHub Releases에서 제공하며, 소용량 집계/예측 파일은 이 저장소에 직접 포함된다.

> **주의**: 이 `data/processed/` 폴더는 구조 문서용으로 생성됐다. 실제 parquet 파일은 `preprocessed_v3/` 경로에 위치한다. Streamlit 앱이 `preprocessed_v3/` 경로를 직접 참조하므로, 다운로드 후 배치 경로를 확인할 것.

---

## 파일 목록

### 직접 Git 포함 (별도 다운로드 불필요)

| 파일 | 크기 | 역할 |
|---|---|---|
| `preprocessed_v3/product_recommendation_scores.parquet` | 0.37MB | 피부타입 맞춤 추천 탭 (tab_skin) 필수 |
| `preprocessed_v3/product_skin_aggregates.parquet` | 0.32MB | 피부타입별 부정 신호 집계 |
| `preprocessed_v3/lstm_v3_preds.parquet` | 4.6MB | BiLSTM v3 전체 데이터 사전 예측 캐시 |
| `preprocessed_v3/transformer_v3_preds.parquet` | 4.6MB | Transformer v3 전체 데이터 사전 예측 캐시 |

### GitHub Releases 제공 (다운로드 필요)

| 파일 | 크기 | 역할 |
|---|---|---|
| `service_reviews.parquet` | 106MB | 서비스 실행 필수 (탭1/2 기반 데이터) |
| `train.parquet` | 119.8MB | BiLSTM/Transformer 학습 재현용 |
| `val.parquet` | 30.3MB | 모델 평가 재현용 |

### 제외 파일 (역할 문서만 유지)

| 파일 | 크기 | 역할 | 제외 이유 |
|---|---|---|---|
| `ambiguous.parquet` | 88.9MB | 별점-텍스트 충돌 22.5% — 학습 제외 대상 | 재생성 가능, 대용량 |
| `train_preview.csv` | 1.8MB | 학습 데이터 샘플 (100건) 미리보기 | 재생성 가능 |
| `ambiguous_preview.csv` | 2.9MB | ambiguous 샘플 (100건) 미리보기 | 재생성 가능 |

---

## Releases 다운로드 경로

GitHub Releases 페이지에서 파일을 다운로드한 후 아래 경로에 배치한다.

```bash
oliveyoung_crawler/
└── preprocessed_v3/
    ├── service_reviews.parquet    ← 여기에 배치
    ├── train.parquet              ← 여기에 배치 (학습 재현 시)
    └── val.parquet                ← 여기에 배치 (학습 재현 시)
```

---

## 전처리 데이터 생성 명령

Releases에서 다운로드하지 않고 직접 생성하려면:

```bash
# 전처리 (KoNLPy Java 필요, ~2시간)
python run_preprocess.py --include-external --output preprocessed_v3

# 서비스 데이터 빌드
python scripts/build_service_reviews.py
python scripts/build_product_skin_aggregates.py
python scripts/build_recommendation_scores.py

# BiLSTM 사전 추론
python precompute_preds.py
```

---

## 데이터 구성

### service_reviews.parquet 주요 컬럼

| 컬럼 | 설명 |
|---|---|
| review_id | 리뷰 고유 ID |
| platform | OliveYoung / Musinsa / Coupang |
| product_id | 상품 ID |
| product_name | 상품명 |
| brand | 브랜드명 |
| category | 카테고리 |
| rating | 별점 |
| clean_review | 정제된 리뷰 텍스트 |
| tokens_str | Okt 형태소 분석 결과 (공백 구분 문자열) |
| sentiment_label | 약한 라벨 (positive/negative/neutral) |
| base_skin_type | 정규화된 피부타입 (건성/지성/복합성/민감성/중성/null) |

### product_recommendation_scores.parquet 주요 컬럼

| 컬럼 | 설명 |
|---|---|
| product_id | 상품 ID |
| product_name | 상품명 |
| brand | 브랜드명 |
| base_skin_type | 피부타입 |
| recommendation_score | 추천 점수 (0~100) |
| skin_negative_rate | 해당 피부타입에서 부정 신호 비율 |
| skin_review_count | 해당 피부타입 리뷰 건수 |
| evidence_level | strong/limited/insufficient |
| recommendation_tier | strong_candidate / caution_check 등 |

---

## 플랫폼별 구성

| 플랫폼 | 전체 건수 | 비율 |
|---|---|---|
| OliveYoung | ~270K | 67.1% |
| Musinsa | ~100K | 24.9% |
| Coupang | ~32K | 8.0% |
| **전체** | **402,438** | 100% |

---

## ambiguous 데이터 역할

`ambiguous.parquet`는 별점과 텍스트 감성이 충돌하는 리뷰 (전체의 22.5%)다.  
학습에서 제외됐으며, 라벨 노이즈 분석이나 오분류 연구에 활용할 수 있다.  
재생성이 가능하고 용량이 크기 때문에 Releases에도 포함하지 않는다.  
필요하면 전처리를 다시 실행하면 된다.
