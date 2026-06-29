# 서비스 설계 — Streamlit 기반 화장품 리뷰 분석 서비스

---

## 1. 서비스 문제 정의

화장품 플랫폼의 종합 별점과 긍정 리뷰 비율은 "일반적으로 좋다"는 신호다. 그런데 화장품은 피부타입에 따라 반응이 달라진다. 건성 피부에 좋은 제품이 지성 피부에는 트러블을 일으킬 수 있다.

이 서비스는 "내 피부타입에서 부정 신호가 많은 리뷰는 없는가"를 확인하는 기능을 제공한다. 전체 리뷰 별점 대신, 같은 피부타입 리뷰에서 모델이 부정으로 감지한 비율을 기준으로 상품을 평가한다.

**핵심 한계 먼저**: 모델은 약한 라벨(별점+텍스트 규칙)로 학습됐으며, 모든 예측은 참고용이다. 모델이 "부정 감지"한 리뷰가 실제로 부정인 리뷰가 아닐 수 있다 (특히 neutral 클래스). 서비스는 이 한계를 UI에서 명시한다.

---

## 2. 데이터 흐름 요약

```
[원본 데이터]
output/*.jsonl (OliveYoung 직접 수집)
data/external/*.csv (Musinsa/Coupang → normalize_external.py 변환)
        ↓
[전처리]
preprocessed_v3/train.parquet (학습용)
preprocessed_v3/val.parquet (평가용)
preprocessed_v3/service_reviews.parquet (서비스용 전체)
preprocessed_v3/ambiguous.parquet (학습 제외, 분석용)
        ↓
[사전 추론]
precompute_preds.py → lstm_v3_preds.parquet (BiLSTM 예측 캐시)
precompute_transformer.py → transformer_v3_preds.parquet (Transformer 예측 캐시)
        ↓
[집계]
service_reviews.parquet + lstm_v3_preds.parquet
→ scripts/build_service_reviews.py → [merged] (탭1/2 기반 데이터)

scripts/build_product_skin_aggregates.py → product_skin_aggregates.parquet
scripts/build_recommendation_scores.py → product_recommendation_scores.parquet
        ↓
[Streamlit]
streamlit_app_v2.py (5개 탭)
```

---

## 3. Streamlit 5개 탭 구조

### 탭 목록

| 탭 ID | 이름 | 주요 기능 | 필수 데이터 파일 |
|---|---|---|---|
| tab_skin | 피부타입 맞춤 추천 | 피부타입별 부정 신호 낮은 상품 추천 | `product_recommendation_scores.parquet` |
| tab1 | 일반 상품 추천 | 부정 신호 비율 기반 상품 리스트 | `service_reviews.parquet` + BiLSTM 예측 |
| tab2 | 상품 비교 | 상품 2개 병렬 부정 신호 비교 | `service_reviews.parquet` + BiLSTM 예측 |
| tab3 | 모델·데이터 리포트 | 학습 지표, 혼동 행렬, 하이퍼파라미터 | `reports/` 폴더의 json/csv 파일들 |
| tab4 | 리뷰 직접 분석 | 사용자 입력 텍스트 3개 모델 실시간 추론 | Baseline + BiLSTM + Transformer 모델 |

### tab_skin — 피부타입 맞춤 추천

`product_recommendation_scores.parquet`에서 선택한 피부타입에 해당하는 행을 필터링하여 점수 내림차순으로 정렬한다.

표시 정보:
- 상품명, 브랜드, 카테고리
- 추천 점수 (0~100)
- 피부타입별 리뷰 건수 및 부정 신호 비율
- evidence_level (strong/limited/insufficient)
- 추천 tier 배지

Coupang 데이터는 피부타입 정보가 없어서 이 탭 집계에서 제외됐다. UI에 이 사실을 안내한다.

### tab1 — 일반 상품 추천

전체 플랫폼 + 사용자 필터 기준으로 부정 신호 비율(LSTM 예측 기준)을 집계하여 상품별로 표시한다.

정렬 옵션: 부정 신호 비율 낮은순, 리뷰 건수 많은순, 평균 별점 높은순

### tab2 — 상품 비교

상품 2개를 선택해 나란히 비교한다.
- 부정 신호 비율, 별점 분포, 리뷰 건수
- 피부타입별 부정 신호 비율 비교 (base_skin_type 있는 리뷰만)

### tab3 — 모델·데이터 리포트

`reports/` 폴더에서 파일을 로딩하여 표시한다.
- 모델별 정확도, macro_f1, 클래스별 정밀도/재현율
- 혼동 행렬 시각화
- 학습 히스토리 (epoch별 loss/accuracy)
- 데이터 분포 통계

### tab4 — 리뷰 직접 분석

사용자가 직접 리뷰 텍스트를 입력하면 3개 모델로 실시간 추론한다.

| 모델 | 입력 전처리 | 출력 |
|---|---|---|
| Baseline (TF-IDF+LogReg) | Okt 형태소 분석 | positive/negative/neutral 확률 |
| BiLSTM | Okt 형태소 분석 → tokens_str | positive/negative/neutral 확률 |
| Transformer (KLUE-BERT) | AutoTokenizer (원문 입력) | positive/negative/neutral 확률 |

KoNLPy/Java 미설치 환경에서는 Okt 대신 한글 문자 필터링으로 fallback된다. 기능은 유지되지만 분석 정밀도가 낮아진다는 안내를 UI에 표시한다.

---

## 4. 데이터 로딩 구조

```python
@st.cache_data  # 세션 간 데이터 캐시 (parquet)
def load_recommendation_scores():
    return pd.read_parquet("preprocessed_v3/product_recommendation_scores.parquet")

@st.cache_resource  # 세션 간 모델 캐시 (무거운 객체)
def load_lstm_v3():
    model = tf.keras.models.load_model("models/lstm_final_v3.keras")
    vocab = load_vocab("models/lstm_final_v3_vocab.txt")
    return model, vocab
```

`@st.cache_data`는 parquet/csv 같은 직렬화 가능한 데이터에 사용한다.  
`@st.cache_resource`는 TensorFlow 모델, Transformer 파이프라인 같이 직렬화하면 안 되는 객체에 사용한다.

첫 모델 로딩은 30~60초가 소요된다. 이후 세션 내에서는 캐시를 사용한다.

---

## 5. 전역 필터 동작

사이드바에 platform → category → brand 순으로 cascade 필터가 있다.

```
platform 선택 (OliveYoung / Musinsa / Coupang / 전체)
    ↓
category 선택 (skincare / maskpack / cleansing / suncare)
    ↓
brand 선택 (선택된 platform+category 내의 brand 목록)
```

상위 선택이 바뀌면 하위 선택이 자동으로 초기화된다 (session_state 관리). 이렇게 하지 않으면 "OliveYoung → 설화수"를 선택한 상태에서 platform을 Musinsa로 바꿨을 때 brand 필터가 "설화수"로 남아 결과가 0건이 되는 문제가 발생한다.

---

## 6. 사전 예측 + fallback 실시간 추론 연결

탭1/2 집계의 핵심은 `service_reviews.parquet`에 BiLSTM 예측값이 합쳐진 데이터다.

```
service_reviews.parquet (review_id, clean_review, skin_type, ...)
+
lstm_v3_preds.parquet (review_id, lstm_pred_label, lstm_pred_prob)
→ merge on review_id
→ tab1/2에서 상품별 부정 신호 비율 집계
```

`lstm_v3_preds.parquet`가 없으면 `precompute_preds.py`를 먼저 실행해야 한다. 파일이 없을 때는 실시간 배치 추론으로 대체되지만 속도가 매우 느리다.

---

## 7. "모델 부정 감지", "부정 신호 리뷰" 표현 사용 이유

서비스에서 "부정 리뷰"라는 표현 대신 "모델 부정 감지 리뷰", "부정 신호 리뷰"라고 표현한다.

이유:
1. 모델은 약한 라벨로 학습됐으며 neutral_precision=0.196 수준이다. neutral로 예측된 리뷰 중 상당수가 실제로 neutral이 아닐 수 있다.
2. "부정 리뷰"라고 표현하면 모델 예측이 사실인 것처럼 오해될 수 있다.
3. "모델 부정 감지"는 "이 모델이 부정으로 분류했다"는 의미를 명확히 전달한다.

---

## 8. Coupang 피부타입 추천 제외 이유

Coupang 데이터에는 skin_type 컬럼이 없다. 전체 32K건의 base_skin_type 커버리지가 0.0%다.

피부타입 추천 탭은 피부타입별 부정 신호 비율을 집계해서 상품을 추천한다. 피부타입 정보가 없는 데이터를 집계에 포함시키면 "피부타입 정보가 없는 Coupang 리뷰"가 집계에 0으로 기여하여 점수를 희석시키는 문제가 생긴다.

따라서 피부타입 추천 탭에서는 OliveYoung + Musinsa 데이터만 사용한다. tab_skin의 UI에서 이 사실을 안내한다.

---

## 9. KoNLPy 미설치 환경 fallback

탭4 실시간 분석에서 Baseline과 BiLSTM은 Okt 형태소 분석이 필요하다.

KoNLPy 미설치 (또는 Java 미설치) 환경에서는:
```python
try:
    from konlpy.tag import Okt
    okt = Okt()
    tokens = okt.morphs(text, stem=True)
except Exception:
    # fallback: 한글 문자만 추출, 공백 분리
    tokens = re.findall(r'[가-힣]+', text)
```

fallback 모드에서는 형태소 분석 없이 한글 문자만 추출하므로, 어미/조사가 포함된 토큰이 입력된다. 분석 정밀도가 낮아지지만 앱 자체는 오류 없이 동작한다. UI에 "KoNLPy 미설치 — 분석 정밀도 제한됨" 안내를 표시한다.

Transformer (KLUE-BERT)는 AutoTokenizer를 직접 사용하므로 KoNLPy가 필요 없다.
