# 개발 과정 기록 — 실제로 확인한 것과 내린 판단

> 이 문서는 개발 중 실제 파일을 열어보고 수치를 확인하면서 내린 판단의 흐름을 기록한다.  
> 확인하지 않은 내용은 쓰지 않는다.

---

## 1. 크롤링 데이터를 그대로 믿으면 안 된다

**확인한 파일**: `reports/service_reviews_manual_review_samples.md`

BiLSTM v3으로 부정(negative)으로 예측된 샘플 중에서 수동으로 검수한 사례가 있다.

| 별점 | 약한 라벨 | LSTM 예측 | 실제 리뷰 |
|---|---|---|---|
| ★4 | positive | **negative** | "자극없는데 눈에 따가워요, 다이소 토너 쓸듯" |
| ★5 | positive | **negative** | "코 옆에 살짝 따가워요" |

★4~5 별점임에도 LSTM이 부정으로 예측한 케이스를 직접 보고 나서야, "별점 높으면 긍정"이라는 전제가 충분하지 않음을 확인했다.

**내린 판단**: 별점 기반 라벨만으로는 텍스트 내용을 충분히 반영하지 못한다. 별점+텍스트 교차 검증이 필요하다.

이 판단이 4계층 키워드 라벨링 설계의 출발점이 됐다.

---

## 2. 별점 오기(誤記) 사례가 실제로 존재한다

**확인한 파일**: `inspect_low_rating_lstm_pos_out.txt`, 직접 샘플 50건 검수

★1~2인데 LSTM이 positive로 예측하는 케이스 300건을 분석했다. 50건을 직접 열어봤을 때:
- 48/50건: 실제로 불만족 내용. "배송 실수", "피부 트러블", "환불 요청" 등
- 2/50건: 실제로 긍정 내용

별점 1~2인데 LSTM이 positive로 예측한 대부분 케이스가 실제로는 부정 내용이었다. 즉, LSTM이 별점보다 텍스트 내용을 더 정확히 반영한 경우다.

반대로, 이 중 일부(약 4% 추산)는 실제로 "긍정 내용인데 별점을 낮게 준" 케이스로 판단했다. 이런 케이스는 수용할 수밖에 없다.

**내린 판단**: ★1~2+mixed(텍스트 규칙 상 긍정인 케이스) 6,475건을 `negative`로 복구한다. 50건 직접 검수 결과 48/50건이 부정이므로 통계적으로 충분한 근거다.

이 판단이 `labeling.py`의 `_finalize_label()` 로직 수정으로 이어졌다.

---

## 3. 플랫폼별 데이터 구조가 다르다

**확인한 파일**: `reports/normalization_check.md`

세 플랫폼의 skin_type 데이터를 직접 확인한 결과:

| 플랫폼 | base_skin_type 있는 비율 |
|---|---|
| OliveYoung | 39.3% |
| Musinsa | 62.9% |
| **Coupang** | **0.0%** |

Coupang은 skin_type 컬럼이 API 응답에 없다. 빠진 게 아니라 아예 수집 구조에 없었다.

**내린 판단**: Coupang 데이터 전체를 피부타입 기반 집계에서 제외한다. 강제로 집계에 포함시키면 "데이터 없음"이 집계에 희석되어 신뢰할 수 없는 점수가 나온다.

이 판단이 `recommendation/aggregation.py`에 반영됐다. Coupang 데이터는 일반 추천 탭(탭1/2)에만 사용하고, 피부타입 맞춤 추천에서는 제외된다.

---

## 4. 전체의 절반이 피부타입 데이터가 없다

**확인한 파일**: `reports/normalization_check.md`

전체 402,438건 중 base_skin_type이 있는 비율: 47.1%

- OliveYoung 39.3% × OliveYoung 비율 + Musinsa 62.9% × Musinsa 비율 + Coupang 0% × Coupang 비율 = 전체 47.1%

**내린 판단**: 이 한계를 서비스에서 명시한다. 피부타입 추천 탭은 전체 리뷰의 47.1%를 기반으로 한다. 나머지 52.9%는 피부타입 정보가 없어서 집계에서 제외된다.

`evidence_level` 계층(sufficient/limited/insufficient)을 도입한 이유도 여기에 있다. 피부타입별 리뷰가 5건 미만이면 점수 신뢰도가 낮다는 것을 점수에 반영했다.

---

## 5. skin_type 정규화가 필요했다

**확인한 파일**: `reports/normalization_check.md`, `recommendation/normalization.py`

OliveYoung의 skin_type 원문 예시:
- "복합성 · 진정/보습"
- "지성 · 모공/피지"
- "민감성 · 자극없는"

한 필드에 피부타입과 피부 고민이 섞여 있었다. 단순히 '복합성'으로 집계하려면 파싱이 필요했다.

**내린 판단**: `·`를 기준으로 분리하여 첫 부분을 `base_skin_type`(건성/지성/복합성/민감성/중성), 뒷부분을 `skin_need_tags`(진정/보습 등)로 분리한다.

base_skin_type 추출 성공률: 99.6%. 나머지 0.4%는 "민감" → "민감성" 등 표현 변형 케이스로, 별도 매핑 테이블로 처리했다.

---

## 6. 키워드 수가 17개로는 부족했다

**확인한 파일**: `edge_case_analysis.txt`

초기 NEGATIVE_KEYWORDS 17개로 라벨링한 결과를 실측했다.

- "효과 없" (공백 있음): 1,023건 포착 O
- "효과가 없" (조사 포함): 865건 포착 **X**
- "효과를 보지 못": 137건 포착 **X**
- "무슨/어떤/아무 효과" (수사적 의문): 155건 포착 **X**

한국어에서 조사가 붙으면 같은 의미의 표현이 전혀 다른 문자열이 된다. "효과 없"과 "효과가 없"은 다른 문자열이지만 의미는 동일하다.

**내린 판단**: NEGATIVE_KEYWORDS를 55개로 확장하여 조사 변형, 붙여쓰기, 어미 변형을 수동으로 추가했다.

이 확장은 자동화하기 어렵다. 한국어 어미 변형과 조사 결합은 규칙이 복잡하므로, 이번에는 실측 데이터를 보고 수동으로 추가하는 방식을 선택했다.

---

## 7. 한 번에 전체 학습을 돌리면 오류 탐지가 늦다

**확인한 파일**: `transformer_v3_train.err`

Transformer v1 학습 때 설정 오류로 몇 시간을 낭비했다.

`transformer_v3_train.err` 분석 결과: Windows 환경에서 `dataloader_num_workers>0`으로 설정 시 멀티프로세스 데드락이 발생하는 경고가 있었다. v1 학습 중에 이 문제가 발생해서 학습이 중단됐다.

**내린 판단**: 전체 학습 전에 반드시 `--sample 5000 --epochs 1` 스모킹 테스트를 먼저 실행한다. 설정 오류가 있으면 5,000건 실행 중 바로 드러난다. 이를 통해:
- `dataloader_num_workers=0` 설정 확인
- `fp16=False` 설정 확인 (Windows GPU 불안정)
- 배치 크기 메모리 오류 확인

v3부터 이 절차를 먼저 적용했고, 문제없이 통과한 뒤 전체 학습을 실행했다.

---

## 8. neutral 클래스가 모델에서 무시된다

**확인한 파일**: `reports/lstm_final_v3_metrics.json`, `reports/lstm_final_v3_classification_report.csv`

LSTM v1 학습 후 평가 지표를 열어보니:

- positive recall: 0.994
- negative recall: 0.742
- **neutral recall: 0.242**

neutral 리뷰가 전체의 3.2%밖에 없어서 모델이 neutral를 거의 예측하지 않았다. class_weight=balanced를 적용하지 않으면 "positive만 예측해도 accuracy가 높다"는 함정에 빠진다.

**내린 판단**: class_weight=balanced를 적용한다. 결과:

- LSTM v3 neutral recall: 0.586 (v1 0.242에서 개선)
- 단, neutral_precision: 0.196 (낮음)

class_weight=balanced는 neutral recall을 올리지만 neutral precision을 낮춘다. trade-off를 수용했다. 이유: 서비스 목적은 부정 신호 탐지이므로, neutral 과예측(false positive)이 부정 신호 탐지에 미치는 영향이 제한적이라 판단했다.

---

## 9. 모델 수치만 보면 안 된다

**확인한 파일**: `reports/service_reviews_manual_review_samples.md`, `inspect_ambiguous_lstm_output.txt`

LSTM v3 accuracy=0.893은 숫자로 보면 양호해 보인다. 그런데 `inspect_ambiguous_lstm_output.txt`를 열어보니:

ambiguous 집합(학습에서 제외된 22.5%) 중 300건 샘플의 LSTM 예측 분포:
- neutral 예측: 103건
- positive 예측: 189건
- negative 예측: 8건

ambiguous 집합은 "별점과 텍스트가 충돌하는" 데이터다. 그 중 positive 예측이 189건(63%)이나 된다는 것은 neutral 과예측(accuracy 지표에서 안 보이는 문제)과는 별도로, 경계 케이스에서의 모델 행동을 직접 확인한 것이다.

확인 후 내린 판단: accuracy나 macro_f1만으로 모델을 평가하면 안 된다. 특히 서비스에 사용되기 전에 실제 리뷰 샘플을 직접 보고 "이 예측이 맞는가"를 확인해야 한다.

`service_reviews_manual_review_samples.md`에서 181건을 직접 확인한 이유가 여기에 있다.

---

## 10. 모델 예측을 서비스에서 단정적으로 표현하면 안 된다

**확인한 파일**: `recommendation/scoring.py`, `streamlit_app.py`

모델이 예측한 감성 라벨을 그대로 "부정 리뷰", "이 상품은 안 맞아요" 식으로 표현하면 오해를 준다.

LSTM v3 neutral_precision=0.196은 "neutral로 예측된 리뷰 중 80%가 실제로 neutral이 아닐 수 있다"는 뜻이다. 이런 모델 예측을 사실 정보처럼 표현하는 것은 적절하지 않다.

**내린 판단**: 서비스 전반에서 아래 표현 방식을 적용한다.

| 금지 표현 | 사용 표현 |
|---|---|
| "부정 리뷰" | "모델 부정 감지", "부정 신호 리뷰" |
| "이 상품은 문제 있음" | "부정 신호 비율이 높음" |
| "이 피부타입에 맞지 않음" | "해당 피부타입에서 부정 신호 리뷰 비율이 높음" |
| "안전한 상품" | "부정 신호가 낮은 상품" |

이 표현 방식이 `scoring.py`의 tier 이름(`strong_candidate`, `caution_check`, `negative_review_first`)과 `streamlit_app.py`의 UI 텍스트에 반영됐다.

---

## 11. clone 후 즉시 실행이 불가능하다

**확인한 파일**: `.gitignore`, `preprocessed_v3/` 폴더 크기

GitHub에 올릴 수 있는 단일 파일 크기 제한은 100MB다. 그런데:
- `service_reviews.parquet`: 106MB
- `train.parquet`: 119.8MB
- `lstm_final_v3.keras`: 119MB
- `transformer_final_v3/model.safetensors`: 422MB

이 파일들 없이는 Streamlit 주요 기능이 동작하지 않는다.

**내린 판단**: GitHub Releases를 활용한다. 대용량 파일을 Releases에 업로드하고, README에서 다운로드 위치와 배치 경로를 안내한다.

동시에 3가지 실행 모드를 설계했다:
- **모드 A**: 소용량 parquet만 사용 → 피부타입 추천 탭만 동작
- **모드 B**: Releases에서 service_reviews + BiLSTM 모델 다운로드 → 주요 기능 동작
- **모드 C**: 전체 데이터 + 전체 모델 → 전체 재현

모드 A는 git clone 직후 추가 다운로드 없이 바로 실행할 수 있다. `product_recommendation_scores.parquet`(0.37MB)와 `product_skin_aggregates.parquet`(0.32MB)는 직접 git에 포함했기 때문이다.

---

## 12. supplement_negative.py 실행 이력

**확인한 파일**: `supplement_negative.py`

부정 리뷰 비율이 전체의 9.3%로 낮았다. 클래스 불균형을 완화하기 위해 OliveYoung에서 별점 낮은순(RATING_ASC)으로 정렬해 추가 수집을 시도했다.

`supplement_negative.py` 코드 확인 결과: 이미 수집된 `output_recovered_2026-06-21/` 폴더를 대상으로, `seen_ids`로 중복 제거하면서 새로운 부정 리뷰를 추가 수집한다.

이 스크립트는 실제로 실행됐다. 결과 데이터(`output_recovered_2026-06-21/`)는 v3 전처리에 반영 완료됐다. 이후 `output_recovered_2026-06-21/`는 중간 산출물로 제외했다.

**내린 판단**: 추가 수집된 부정 리뷰가 v3 학습 데이터에 반영됐다. 클래스 불균형이 완전히 해소되지는 않았지만 (negative 9.3%), class_weight=balanced와 조합하여 수용 가능한 수준으로 학습했다.

---

## 13. JSONL 복구 이력

**확인한 파일**: `recover_jsonl.py`

크롤링 중 일부 JSONL 파일이 손상됐다 (2026-06-21). `recover_jsonl.py`로 복구 작업을 수행했다.

복구 방식: 손상된 줄을 건너뛰고 파싱 가능한 JSON 줄만 추출하여 새 파일에 저장.

복구 완료 후 `output_recovered_2026-06-21/`에 저장됐고, 이것이 v3 전처리의 입력이 됐다. 복구 과정에서 손실된 리뷰 수는 전체 대비 미미한 수준으로 확인했다.

---

## 14. UI 개선 단계별 백업 파일 역할

**확인한 파일**: `streamlit_app_v2_backup_step5a.py`, `streamlit_app_v2_backup_step5b.py`, `streamlit_app_v2_backup_step5c.py`, `streamlit_app_v2_backup_step5d.py`

Step 5(Streamlit 개발) 중에 기능 추가 단계마다 백업했다:
- `step5a`: 기본 5탭 구조 + 전역 플랫폼 필터
- `step5b`: cascade 필터(brand) + 상품 비교 탭
- `step5c`: 모델 리포트 탭, 데이터 통계 탭
- `step5d`: 탭4 실시간 분석 + KoNLPy fallback

이 백업 파일들은 UI 개발 중 되돌릴 수 있는 체크포인트였다. 최종 `streamlit_app.py`가 이 단계들을 통합한 결과다. 개발 단계가 git history에도 별도 커밋으로 남아있으므로, 백업 파일 자체는 최종 레포에서 제외한다.
