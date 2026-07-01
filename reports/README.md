# reports/

모델 평가 지표, 실험 이력, 데이터 검수 결과 파일 목록.

---

## 최종 참고 파일

서비스에 반영된 최종 모델(v3)의 평가 결과와 수동 검수 샘플.

| 파일 | 설명 |
|---|---|
| `lstm_final_v3_metrics.json` | BiLSTM v3 최종 평가 지표 (accuracy, macro_f1, neg/neu/pos recall) |
| `lstm_final_v3_classification_report.csv` | BiLSTM v3 분류 리포트 |
| `lstm_final_v3_confusion_matrix.csv` | BiLSTM v3 혼동 행렬 |
| `lstm_final_v3_history.csv` | BiLSTM v3 학습 이력 (epoch별 loss/accuracy) |
| `transformer_final_v3_metrics.json` | Transformer v3 최종 평가 지표 |
| `transformer_final_v3_classification_report.csv` | Transformer v3 분류 리포트 |
| `transformer_final_v3_confusion_matrix.csv` | Transformer v3 혼동 행렬 |
| `transformer_final_v3_history.csv` | Transformer v3 학습 이력 |
| `transformer_final_v3_hyperparameters.json` | Transformer v3 학습 하이퍼파라미터 |
| `service_reviews_manual_review_samples.md` | 서비스 리뷰 수동 검수 샘플 (181건) |
| `recommendation_scores_check.md` | 추천 점수 검수 결과 |
| `product_skin_aggregates_check.md` | 피부타입 집계 검수 결과 |

---

## 실험 이력 파일

v1·v2 실험 및 중간 단계 결과. 최종 모델 선정 근거로 보존.

| 파일 패턴 | 설명 |
|---|---|
| `lstm_none_*` | BiLSTM — class_weight 없이 학습 |
| `lstm_balanced_*` | BiLSTM — class_weight=balanced |
| `lstm_balanced_e3_earlystop_*` | BiLSTM balanced, epochs=3 EarlyStopping |
| `lstm_none_e3_earlystop_*` | BiLSTM none, epochs=3 EarlyStopping |
| `lstm_final_v2_*` | BiLSTM v2 (외부 데이터 추가 전 버전) |
| `transformer_final_v2_*` | Transformer v2 (키워드 55개 확장 전 버전) |
| `baseline_none_*` | TF-IDF Baseline — class_weight 없음 |
| `baseline_balanced_*` | TF-IDF Baseline — class_weight=balanced |
| `normalization_*` | skin_type 정규화 검수 결과 |
| `*_manual_review_samples.*` | 각 단계별 수동 검수 샘플 |
