# Recommendation Scores Check Report

생성 시각: 2026-06-27T21:42:45.560050

## 1. 기본 수치
- 전체 row 수: 6,008
- 고유 product 수: 1,521
- 플랫폼별 분포:
  - musinsa: 2,275 (37.9%)
  - oliveyoung: 3,733 (62.1%)
  - coupang: 0 (정상 — base_skin_type 없음)

## 2. recommendation_score 분포
- 평균: 70.56
- 표준편차: 19.17
- 최소/최대: 8.82 / 99.82
- P10/P25/P50/P75/P90: 46.92 / 53.15 / 73.68 / 85.53 / 97.32

구간별:
  - (-0.001, 20.0]: 12 (0.2%)
  - (20.0, 40.0]: 300 (5.0%)
  - (40.0, 60.0]: 1,835 (30.5%)
  - (60.0, 80.0]: 1,962 (32.7%)
  - (80.0, 100.0]: 1,899 (31.6%)

## 3. evidence_level 분포
  - limited_evidence: 2,229 (37.1%)
  - strong_evidence: 2,163 (36.0%)
  - insufficient_evidence: 1,616 (26.9%)

## 4. recommendation_tier 분포
  - strong_candidate: 1,825 (30.4%)
  - review_before_buying: 1,774 (29.5%)
  - insufficient_evidence: 1,616 (26.9%)
  - caution_check: 518 (8.6%)
  - negative_review_first: 275 (4.6%)

## 5. rank_exposure_flag / review_first_flag
- rank_exposure_flag=True: 2,082 (34.7%)
- review_first_flag=True: 978 (16.3%)

## 6. base_skin_type별 분포
  - 복합성: 1,461 (24.3%)
  - 건성: 1,392 (23.2%)
  - 지성: 1,383 (23.0%)
  - 민감성: 1,282 (21.3%)
  - 중성: 490 (8.2%)

## 7. 검증 결과
- 입력 검증: 통과
- 출력 검증: 통과
- parquet 재로드 확인: 통과

## 8. rank_exposure_flag 기준 검증
- insufficient_evidence + rank_exposure_flag=True: 0
  (0이어야 정상)

## 9. 서비스 관점 판단
1. 추천 상위 노출 적합 (rank_exposure_flag=True): 2,082 (34.7%)
2. 부정 리뷰 먼저 확인 유도 (review_first_flag=True): 978 (16.3%)
3. 가장 신뢰 가능한 추천군 (strong_evidence + normal): 1,825 (30.4%)
4. 중성 피부 타입 strong_evidence 수: 0건 (희소 데이터 확인)
5. high_negative_signal 전부 review_first_flag=True: True

## 10. 수동 샘플 검수 결과

→ recommendation_scores_manual_review_samples.md 참조
