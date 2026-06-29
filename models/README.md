# models — 모델 파일

---

## 파일 목록

### 직접 Git 포함 (별도 다운로드 불필요)

| 파일 | 크기 | 역할 |
|---|---|---|
| `models/lstm_final_v3_vocab.txt` | 458KB | BiLSTM TextVectorization 어휘 사전 |
| `models/transformer_final_v3/config.json` | 소용량 | KLUE-BERT 모델 구조 설정 |
| `models/transformer_final_v3/tokenizer.json` | 734KB | 토크나이저 어휘 |
| `models/transformer_final_v3/tokenizer_config.json` | 소용량 | 토크나이저 설정 |
| `models/transformer_final_v3/vocab.txt` | 소용량 | 어휘 파일 |
| `models/transformer_final_v3/special_tokens_map.json` | 소용량 | 특수 토큰 맵 |

### GitHub Releases 제공 (다운로드 필요)

| 파일 | 크기 | 역할 |
|---|---|---|
| `tfidf_vectorizer.joblib` | 4.3MB | Baseline TF-IDF 벡터라이저 |
| `baseline_logreg_balanced.joblib` | 2.3MB | Baseline LogisticRegression (class_weight=balanced) |
| `lstm_final_v3.keras` | 119MB | BiLSTM v3 최종 모델 |
| `transformer_final_v3/model.safetensors` | 422MB | KLUE-BERT fine-tuned 모델 가중치 |

---

## Releases 다운로드 및 배치

GitHub Releases 페이지에서 파일을 다운로드한 후 아래 경로에 배치한다.

```
oliveyoung_crawler/
└── models/
    ├── tfidf_vectorizer.joblib                    ← 여기에 배치
    ├── baseline_logreg_balanced.joblib            ← 여기에 배치
    ├── lstm_final_v3.keras                        ← 여기에 배치
    ├── lstm_final_v3_vocab.txt                    ← git 포함 (이미 있음)
    └── transformer_final_v3/
        ├── model.safetensors                      ← 여기에 배치
        ├── config.json                            ← git 포함 (이미 있음)
        ├── tokenizer.json                         ← git 포함 (이미 있음)
        ├── tokenizer_config.json                  ← git 포함 (이미 있음)
        ├── vocab.txt                              ← git 포함 (이미 있음)
        └── special_tokens_map.json                ← git 포함 (이미 있음)
```

---

## 기능별 필요 모델

| 기능 | 필요한 모델 파일 |
|---|---|
| 피부타입 추천 탭 (tab_skin) | 없음 (parquet만 필요) |
| 일반 추천 탭 (tab1) | `lstm_final_v3.keras` + `lstm_final_v3_vocab.txt` |
| 상품 비교 탭 (tab2) | `lstm_final_v3.keras` + `lstm_final_v3_vocab.txt` |
| 모델·데이터 리포트 탭 (tab3) | 없음 (reports/ 폴더만 필요) |
| 탭4 Baseline 분석 | `tfidf_vectorizer.joblib` + `baseline_logreg_balanced.joblib` |
| 탭4 BiLSTM 분석 | `lstm_final_v3.keras` + `lstm_final_v3_vocab.txt` |
| 탭4 Transformer 분석 | `transformer_final_v3/model.safetensors` + tokenizer 파일들 |

---

## 모델 파일 없을 때 동작

| 모델 파일 상태 | 동작 |
|---|---|
| 모두 없음 | tab_skin + tab3만 동작. tab1/2/4에서 오류 메시지 표시 |
| Baseline + BiLSTM 있음 | tab_skin, tab1, tab2, tab3, tab4 (Baseline/BiLSTM 선택) 동작 |
| 전체 있음 | 5개 탭 전체 동작 |

---

## 모델 설명

### Baseline (TF-IDF + LogisticRegression)

- 입력: Okt 형태소 분석 토큰 (tokens_str)
- 특징 추출: TF-IDF (n-gram 1~2)
- 분류: LogisticRegression (class_weight=balanced, max_iter=1000)
- 성능: accuracy=0.9067, macro_f1=0.6692

### BiLSTM v3

- 입력: tokens_str (Okt 형태소 분석 결과)
- 구조: TextVectorization → Embedding(128) → BiLSTM(64) → Dense(3, softmax)
- 파라미터: MAX_TOKENS=80000, SEQUENCE_LENGTH=120, DROPOUT=0.4
- 성능: accuracy=0.8930, macro_f1=0.6659, neg_recall=0.7315

### Transformer v3 (KLUE-BERT)

- 사전학습 모델: klue/bert-base
- 입력: 원문 텍스트 (AutoTokenizer, MAX_LENGTH=160)
- fine-tuning: EPOCHS=5, LR=2e-5, WEIGHT_DECAY=0.01, class_weight=balanced
- 성능: accuracy=0.9637, macro_f1=0.7879, neg_recall=0.8713

---

## 제외된 모델 파일

아래 파일은 이 저장소에 포함하지 않는다.

| 파일/폴더 | 이유 |
|---|---|
| `transformer_final_v3/checkpoint-*/optimizer.pt` (844MB × 4) | 학습 중간 체크포인트, 추론에 불필요 |
| `transformer_final_v2/` | 이전 버전 |
| `transformer_klue-bert-base_balanced/` | 초기 실험 버전 |
| `lstm_final_v2.keras` | 이전 버전 |
| `lstm_balanced.keras`, `lstm_none.keras` | 초기 실험 버전 |
| `baseline_logreg_none.joblib` | balanced 버전이 최종 선택 |

이전 버전 모델의 성능 비교는 `docs/technical_report.md`에 기록되어 있다.

---

## 모델 학습 재현

```bash
# Baseline
python train_baseline.py --class-weight balanced

# BiLSTM (전체 데이터 ~1~3시간)
python train_lstm.py --class-weight balanced

# Transformer KLUE-BERT (GPU 권장)
python train_transformer.py --run-name transformer_final_v3 --epochs 5
```

학습 재현 시 `preprocessed_v3/train.parquet`, `preprocessed_v3/val.parquet`가 필요하다. Releases에서 다운로드.
