# preprocess/

올리브영 리뷰 RNN 감성분석을 위한 전처리 파이프라인.

수업(0526 케라스 텍스트 전처리 + RNN 감성분석) 흐름을 베이스로,
올리브영 리뷰 도메인에 맞춰 확장.

## 흐름

```
output/*.jsonl              크롤러 산출물
        │
        ▼ io.load_reviews          4개 카테고리 통합 로딩
        │
        ▼ cleaning.clean           결측·정제(한글만)·중복·길이 필터
        │
        ▼ labeling.label_by_rating_and_text
                                    별점 후보 라벨 + 본문 감성 단서
        │
        ├─ ambiguous 분리           기본 학습 데이터에서 제외
        │
        ▼ tokenize.tokenize        Okt 형태소 분석 + 불용어 제거
        │
        ▼ split.train_val          stratified 8:2
        │
        ▼
preprocessed/{train,val,ambiguous}.parquet
```

## 실행

```bash
# 전체
python run_preprocess.py

# 일부 카테고리만
python run_preprocess.py --categories skincare maskpack

# 빠른 검증 (앞 5000건)
python run_preprocess.py --sample 5000

```

토큰화는 KoNLPy Okt를 사용한다. 환경에 따라 Java/JVM 설치가 필요할 수 있으므로,
Windows/conda 환경에서는 Java 설치와 PATH 설정을 먼저 확인한다.

## 출력 스키마

```
clean_review   정제 후 텍스트 (한글+공백만)
rating_label   별점 기반 1차 후보 라벨
text_rule_label 규칙 기반 텍스트 감성 단서 (negative/positive/mixed/unknown)
sentiment_label 최종 학습용 라벨
sentiment_id   negative=0, neutral=1, positive=2
label_confidence high / medium / low
label_source   rating_text_agree / rating_based / text_corrected / ambiguous_conflict
is_ambiguous   기본 학습 데이터 제외 여부
ambiguous_reason ambiguous 인 경우에만 충돌 사유 기록
tokens         Okt 토큰 리스트 (List[str])
tokens_str     토큰을 공백으로 join 한 문자열 (csv 검수용)
```

원본 컬럼(product_id, brand, category, skin_type 등)은 그대로 유지해서
다운스트림에서 카테고리·피부타입별 분석에 쓸 수 있게 한다.

## 설계 결정

### 왜 별점만 그대로 쓰지 않는가
별점만으로는 라벨 노이즈가 크다. 한국 리뷰 문화에서는 높은 별점을 주고도
본문에 단점이나 불만을 길게 쓰는 경우가 있다. 예를 들어 5점 리뷰라도
"따갑다", "트러블이 났다", "재구매는 안 할 것 같다" 같은 표현이 있으면
본문 감성은 긍정이라고 보기 어렵다.

해결: 별점을 1차 후보 라벨로 두고, 본문에 드러난 간단한 화장품 리뷰 감성
단서와 비교한다. 별점과 텍스트 단서가 강하게 충돌하는 리뷰는 `ambiguous` 로
분리하고 기본 학습 데이터에서 제외한다.

이 방식은 사람 라벨링을 대체하는 완벽한 방법은 아니다. 다만 별점만 사용하는
것보다 명백히 충돌하는 리뷰를 걸러내어 라벨 노이즈를 줄이기 위한 1차 시도다.

### mixed 는 neutral 과 다르다
`text_rule_label=mixed` 는 긍정 단서와 부정 단서가 함께 잡힌 상태다.
최종 학습 라벨의 `neutral` 과 다르며, 기본 학습 데이터에는 넣지 않고
`ambiguous_reason=mixed_text` 로 분리한다.

### 3점은 어떻게 처리하는가
수업 흐름에 맞춰 3점은 `neutral` 로 둔다. 다만 3점 리뷰의 본문에 명확한
긍정/부정 단서가 있으면 `text_corrected` 로 보정한다. 긍정과 부정 단서가
섞여 있으면 `ambiguous` 로 분리한다.

### 규칙 기반 단서의 한계
`text_rule_label` 은 사람이 직접 붙인 정답이 아니라 간단한 규칙 기반 단서다.
반어법, 신조어, 문맥 의존 표현은 놓칠 수 있다. 가장 정확한 평가는 사람이
본문만 보고 라벨링한 검증셋이지만, 이번 단계에서는 비용 문제로 만들지 않는다.

다만 `자극 없이`, `트러블없`, `끈적임없이`, `밀림 없이` 처럼 부정 단어가
없다는 뜻의 표현은 먼저 보호한다. 이 표현 안의 `자극`, `트러블`, `끈적`,
`밀림` 같은 어간이 다시 부정 단서로 중복 카운트되는 오탐을 줄이기 위해서다.

KNU 감성사전과 도메인 보강 사전은 후속 개선 후보로 남긴다. 지금 기본 흐름은
작은 키워드 규칙으로 명백한 충돌 리뷰를 먼저 분리하는 데 집중한다.

## 파일

| 파일 | 역할 |
|---|---|
| `config.py` | 모든 상수 (경로, 라벨 임계값, 토큰 필터, split 비율) |
| `io.py` | JSONL → DataFrame 로딩 |
| `cleaning.py` | 결측·정제·중복·길이 필터 |
| `labeling.py` | 별점 후보 라벨 + 본문 감성 단서 기반 라벨링 |
| `tokenize.py` | Okt 형태소 분석 + 불용어 제거 |
| `split.py` | stratified train/validation |
| `stopwords.txt` | 한국어 불용어 사전 (리뷰 도메인) |
| `resources/knu_sentiword.json` | KNU 한국어 감성사전 (14,843개) |
| `resources/domain_sentiword.json` | 화장품 도메인 보강 사전 |
