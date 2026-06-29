    # product_skin_aggregates 검증 리포트

    생성 일시: 2026-06-27 15:10:56

    ---

    ## 1. 기본 수치 요약

    | 항목 | 수치 |
    |------|------|
    | service_reviews row 수 | 402,438 |
    | service_reviews product_key 수 | 2,221 |
    | 전체 상품 집계 product 수 | 2,221 |
    | 피부 타입별 집계 row 수 | 6,008 |
    | 피부 타입별 집계 product 수 | 1,521 |
    | 피부 타입 집계 사용 리뷰 수 | 189,665 |
    | 피부 타입 집계 제외 리뷰 수 | 212,773 |
    | product_skin_aggregates.parquet 재로드 row 수 | 6,008 |

    ### 제외 사유별 수

    | 사유 | 건수 |
    |------|------|
    | base_skin_type missing (skin_type_normalization_status == missing) | 211,942 |
    | no_base_skin_type (831건) | 831 |
    | predicted_sentiment null | 0 |

    ---

    ## 2. 피부 타입별 집계 수치

    | 피부 타입 | row 수 | 리뷰 수 | positive | neutral | negative | pos_rate | neg_rate | avg_review | high_neg | insuf |
|----------|--------|--------|---------|--------|---------|--------|--------|----------|---------|-------|
| 지성 | 1383 | 58,062 | 50,144 | 4,749 | 3,169 | 0.864 | 0.055 | 42.0 | 29 | 249 |
| 건성 | 1392 | 37,605 | 33,115 | 2,747 | 1,743 | 0.881 | 0.046 | 27.0 | 89 | 323 |
| 민감성 | 1282 | 18,974 | 16,295 | 1,543 | 1,136 | 0.859 | 0.060 | 14.8 | 114 | 368 |
| 복합성 | 1461 | 74,016 | 66,881 | 4,882 | 2,253 | 0.904 | 0.030 | 50.7 | 41 | 216 |
| 중성 | 490 | 1,008 | 771 | 113 | 124 | 0.765 | 0.123 | 2.1 | 2 | 460 |


    ### caution_level 분포
    - normal: 3599  
- insufficient_evidence: 1616  
- moderate_negative_signal: 518  
- high_negative_signal: 275

    ### confidence_label 분포
    - 참고 가능: 2229  
- 비교적 신뢰 가능: 2163  
- 근거 부족: 1616

    ---

    ## 3. 플랫폼별 수치

    | platform | product_skin_aggregates product 수 | skin aggregate row 수 |
    |----------|-----------------------------------|-----------------------|
    | musinsa | 691 | 2275 |
| oliveyoung | 830 | 3733 |

    > **coupang 확인**: coupang은 base_skin_type 데이터가 없으므로 product_skin_aggregates에 포함되지 않는 것이 정상.
    > 위 테이블에 coupang이 없으면 정상.
    >
    > **musinsa / oliveyoung 확인**: 위 테이블에 포함되어 있으면 정상.

    ---

    ## 4. 상위 상품 테이블

    ### 4-1. total_review_count 상위 20 (전체 상품 기준)
    | 순위 | product_key | product_name | brand | base_skin_type | total_review_count |
|-----|------------|-------------|-------|---------------|---------|
| 1 | musinsa::2959816 | [SET] 다이브인 저분자 히알루론산 세럼 5 | torriden | 건성 | 11221 |
| 2 | musinsa::2172345 | 아토베리어365 크림 80ml | aestura | 복합성 | 5697 |
| 3 | musinsa::1246381 | [+바디워시 증정] 퍼퓸 데오 바디스프레이 2 | dashu | 지성 | 5123 |
| 4 | musinsa::2632600 | 아쿠아 오아시스 토너 300ml | snature | 복합성 | 3075 |
| 5 | musinsa::2172337 | 아토베리어365 로션 150ml | aestura | 민감성 | 3048 |
| 6 | musinsa::2417998 | 리얼 히알루로닉 블루 100 앰플 100ml | wellage | 복합성 | 2856 |
| 7 | musinsa::2638240 | [2EA] 아쿠아 콜라겐 펩타이드 EX 멀티  | dewytree | 복합성 | 2820 |
| 8 | musinsa::6239507 | 피브 하이퍼 하이드로 세럼 100ml | feev | 지성 | 2656 |
| 9 | musinsa::3098201 | [사은품 증정] (대용량) 레티놀 시카 흔적  | innisfree | 복합성 | 2631 |
| 10 | musinsa::2775186 | 어드밴스드 더 비타민씨 23 세럼 | cosrx | 민감성 | 2444 |
| 11 | musinsa::2725216 | [SET] 다이브인 저분자 히알루론산 크림 8 | torriden | 복합성 | 2438 |
| 12 | musinsa::2822853 | [무신사단독] 포 맨 1025 독도 올인원 플 | roundlab | 건성 | 2356 |
| 13 | musinsa::1218467 | 1025 독도 토너 500ml(+독도 클렌저  | roundlab | 복합성 | 2287 |
| 14 | musinsa::6239322 | 스킨 베리어 카밍 로션 이엑스 220ml | ongredients | 지성 | 2189 |
| 15 | musinsa::2436679 | 순정 디렉터 선크림 2pack 기획세트 | etude | 지성 | 2007 |
| 16 | musinsa::1532646 | 스킨 워시 500ml | ulos | 지성 | 1791 |
| 17 | musinsa::3162357 | 원더 히알루론산 촉촉 앰플 100ml(+히알루 | tonymoly | 지성 | 1769 |
| 18 | musinsa::2496302 | 그린 마일드 업 선 플러스 50mL 2개 | drg | 지성 | 1766 |
| 19 | musinsa::3578031 | [SET] 다이브인 저분자 히알루론산 수딩크림 | torriden | 복합성 | 1757 |
| 20 | musinsa::3748858 | [무신사 단독] [2pack] 소나무 진정 시 | roundlab | 민감성 | 1687 |


    ### 4-2. skin_review_count 상위 20
    | 순위 | product_key | product_name | brand | base_skin_type | skin_review_count |
|-----|------------|-------------|-------|---------------|---------|
| 1 | musinsa::2959816 | [SET] 다이브인 저분자 히알루론산 세럼 5 | torriden | 복합성 | 3924 |
| 2 | musinsa::2172345 | 아토베리어365 크림 80ml | aestura | 복합성 | 2410 |
| 3 | musinsa::2959816 | [SET] 다이브인 저분자 히알루론산 세럼 5 | torriden | 지성 | 2018 |
| 4 | musinsa::2959816 | [SET] 다이브인 저분자 히알루론산 세럼 5 | torriden | 건성 | 1642 |
| 5 | musinsa::2172345 | 아토베리어365 크림 80ml | aestura | 건성 | 1369 |
| 6 | musinsa::2638240 | [2EA] 아쿠아 콜라겐 펩타이드 EX 멀티  | dewytree | 복합성 | 1113 |
| 7 | musinsa::2172337 | 아토베리어365 로션 150ml | aestura | 복합성 | 1107 |
| 8 | musinsa::2632600 | 아쿠아 오아시스 토너 300ml | snature | 복합성 | 1098 |
| 9 | musinsa::6239507 | 피브 하이퍼 하이드로 세럼 100ml | feev | 복합성 | 1092 |
| 10 | musinsa::2417998 | 리얼 히알루로닉 블루 100 앰플 100ml | wellage | 복합성 | 1058 |
| 11 | musinsa::2725216 | [SET] 다이브인 저분자 히알루론산 크림 8 | torriden | 복합성 | 1013 |
| 12 | musinsa::6239322 | 스킨 베리어 카밍 로션 이엑스 220ml | ongredients | 복합성 | 927 |
| 13 | musinsa::1246381 | [+바디워시 증정] 퍼퓸 데오 바디스프레이 2 | dashu | 복합성 | 909 |
| 14 | musinsa::3098201 | [사은품 증정] (대용량) 레티놀 시카 흔적  | innisfree | 복합성 | 886 |
| 15 | musinsa::6239507 | 피브 하이퍼 하이드로 세럼 100ml | feev | 지성 | 863 |
| 16 | musinsa::2172345 | 아토베리어365 크림 80ml | aestura | 지성 | 846 |
| 17 | musinsa::1246381 | [+바디워시 증정] 퍼퓸 데오 바디스프레이 2 | dashu | 지성 | 844 |
| 18 | musinsa::2822853 | [무신사단독] 포 맨 1025 독도 올인원 플 | roundlab | 복합성 | 815 |
| 19 | musinsa::2775186 | 어드밴스드 더 비타민씨 23 세럼 | cosrx | 복합성 | 790 |
| 20 | musinsa::3162357 | 원더 히알루론산 촉촉 앰플 100ml(+히알루 | tonymoly | 복합성 | 783 |


    ### 4-3. skin_negative_rate 상위 20 (전체)
    | 순위 | product_key | product_name | brand | base_skin_type | skin_negative_rate |
|-----|------------|-------------|-------|---------------|---------|
| 1 | oliveyoung::A000000184159 | [추가증정기획/뽀송 무기자차] 메이크프렘 유브 | 메이크프렘 | 중성 | 1.0000 |
| 2 | musinsa::2757203 | 바디워시 바디로션 2 pack (샌달우드/블랙 | longtake | 복합성 | 1.0000 |
| 3 | oliveyoung::A000000250764 | [역대급증정/자극제로/쌀뜨물클렌징밀크] 에스네 | 에스네이처 | 중성 | 1.0000 |
| 4 | musinsa::6226471 | 맑은쌀선크림 : 고아미+프로바이오틱스 (SPF | beautyofjoseon | 민감성 | 1.0000 |
| 5 | musinsa::6023311 | 문제성 손발톱 집중 케어 2종 세트 | withshyan | 복합성 | 1.0000 |
| 6 | oliveyoung::A000000237449 | [수지pick/뽀용뇽 공동개발] 아누아 피디알 | 아누아 | 중성 | 1.0000 |
| 7 | oliveyoung::A000000251033 | [NEW/쿨링&차단] 라운드랩 자작나무 수분  | 라운드랩 | 중성 | 1.0000 |
| 8 | oliveyoung::A000000158243 | 브링그린 프레시볼 팩 8g 8종 | 브링그린 | 중성 | 1.0000 |
| 9 | oliveyoung::A000000253334 | [포켓몬 에디션] 닥터지 그린마일드 업 선 플 | 닥터지 | 중성 | 1.0000 |
| 10 | oliveyoung::A000000175069 | [곽민경PICK/단독기획] CKD 겔마스크 4 | CKD | 중성 | 1.0000 |
| 11 | musinsa::6337083 | 아쿠아 365 유브이 글로우 핏 톤업선 40m | snature | 지성 | 1.0000 |
| 12 | oliveyoung::A000000161581 | [누적판매 1700만]스킨1004 마다가스카르 | 스킨1004 | 중성 | 1.0000 |
| 13 | oliveyoung::A000000223239 | 식물나라 제주 탄산수 딥 클렌징티슈 80매 | 식물나라 | 중성 | 1.0000 |
| 14 | oliveyoung::A000000247573 | [5월올영픽] [스킨부스팅/윤곽관리] 메디큐브 | 메디큐브 에이지알 | 민감성 | 1.0000 |
| 15 | oliveyoung::A000000162279 | [1등필링/화잘먹] 닥터지 브라이트닝 필링젤  | 닥터지 | 중성 | 1.0000 |
| 16 | oliveyoung::A000000248305 | [NEW] 라로슈포제 안뗄리오스 선 플루이드  | 라로슈포제 | 건성 | 1.0000 |
| 17 | oliveyoung::A000000237728 | [1등 진정세럼] 파넬 시카마누 92세럼 30 | 파넬 | 중성 | 1.0000 |
| 18 | oliveyoung::A000000254249 | [최초구성/케이스증정] 라운드랩 자작나무 수분 | 라운드랩 | 건성 | 1.0000 |
| 19 | oliveyoung::A000000165598 | [더블기획/1+1] 토리든 다이브인 히알루론산 | 토리든 | 중성 | 1.0000 |
| 20 | oliveyoung::A000000223233 | [선크림 세정]식물나라 제주 탄산수 딥 모공  | 식물나라 | 중성 | 1.0000 |


    ### 4-4. skin_negative_rate 상위 20 (skin_review_count >= 5)
    | 순위 | product_key | product_name | brand | base_skin_type | skin_negative_rate |
|-----|------------|-------------|-------|---------------|---------|
| 1 | oliveyoung::A000000184368 | [모공&블랙헤드/노란티스] 티스 딥 오프 클렌 | 티스 | 민감성 | 0.8000 |
| 2 | oliveyoung::A000000212570 | 바이오더마 시카비오 크림+ 100ml 기획 ( | 바이오더마 | 건성 | 0.6667 |
| 3 | oliveyoung::A000000254058 | [포켓몬 에디션]VT 리들샷100 에센스 50 | VT | 민감성 | 0.6364 |
| 4 | oliveyoung::A000000120938 | [10매/5종] 아비브 약산성 pH 시트 마스 | 아비브 | 민감성 | 0.6250 |
| 5 | oliveyoung::A000000212555 | [강력차단]식물나라 워터프루프/알로에쿨링 선  | 식물나라 | 중성 | 0.6000 |
| 6 | oliveyoung::A000000166586 | [단독/대용량] 라운드랩 자작나무 수분 크림  | 라운드랩 | 민감성 | 0.6000 |
| 7 | oliveyoung::A000000216311 | [*피지잡는 *약산성클렌저 *클렌징폼] 아벤느 | 아벤느 | 건성 | 0.6000 |
| 8 | oliveyoung::A000000237449 | [수지pick/뽀용뇽 공동개발] 아누아 피디알 | 아누아 | 민감성 | 0.6000 |
| 9 | oliveyoung::A000000231315 | [1+1] 프리메라 마일드 앤 퍼펙트 클렌징  | 프리메라 | 건성 | 0.5714 |
| 10 | oliveyoung::A000000193133 | 브링그린 모델링 팩 28g [티트리 시카/대나 | 브링그린 | 복합성 | 0.5625 |
| 11 | oliveyoung::A000000247726 | [한정기획] 메이크프렘 인테카 수딩크림 70m | 메이크프렘 | 민감성 | 0.5556 |
| 12 | oliveyoung::A000000213921 | [올영단독400ml] 포인트앤 딥 클린 올킬  | 포인트앤 | 건성 | 0.5385 |
| 13 | oliveyoung::A000000251313 | 비건이펙트 청보리 라하 젤 클렌저 205ml  | 비건이펙트 | 건성 | 0.5000 |
| 14 | oliveyoung::A000000184159 | [추가증정기획/뽀송 무기자차] 메이크프렘 유브 | 메이크프렘 | 민감성 | 0.5000 |
| 15 | oliveyoung::A000000206904 | 라로슈포제 시카플라스트 밤 B5+ 100ml  | 라로슈포제 | 민감성 | 0.5000 |
| 16 | oliveyoung::A000000235364 | [3D진동클렌징/모공케어] 메디큐브 에이지알  | 메디큐브 에이지알 | 지성 | 0.5000 |
| 17 | oliveyoung::A000000202947 | [온열소금팩/화잘먹/모공] 토르홉 사우난지앙  | 토르홉 | 민감성 | 0.5000 |
| 18 | oliveyoung::A000000169035 | [올리브영 단독기획] 믹순 콩 에센스 50ml | 믹순 | 민감성 | 0.5000 |
| 19 | oliveyoung::A000000157350 | [트러블모공] 디오디너리 나이아신아마이드 10 | 디오디너리 | 민감성 | 0.5000 |
| 20 | oliveyoung::A000000212570 | 바이오더마 시카비오 크림+ 100ml 기획 ( | 바이오더마 | 민감성 | 0.5000 |


    ### 4-5. skin_negative_rate 상위 20 (skin_review_count >= 20)
    | 순위 | product_key | product_name | brand | base_skin_type | skin_negative_rate |
|-----|------------|-------------|-------|---------------|---------|
| 1 | oliveyoung::A000000193133 | 브링그린 모델링 팩 28g [티트리 시카/대나 | 브링그린 | 복합성 | 0.5625 |
| 2 | oliveyoung::A000000202899 | [스패츌러 증정] 메디힐 블랙헤드 멜팅 클리어 | 메디힐 | 복합성 | 0.4286 |
| 3 | oliveyoung::A000000207439 | [블랙헤드케어템]브링그린 티트리 시카 포어 코 | 브링그린 | 복합성 | 0.4074 |
| 4 | oliveyoung::A000000232304 | [단독기획/대용량] 파티온 노스카나인 트러블  | 파티온 | 지성 | 0.3846 |
| 5 | oliveyoung::A000000224494 | [더보이즈 영훈PICK/트러블1등] 셀라딕스  | 셀라딕스 | 지성 | 0.3810 |
| 6 | oliveyoung::A000000223906 | 식물나라 가벼운 수분 선 젤 60ml 단품/2 | 식물나라 | 건성 | 0.3810 |
| 7 | oliveyoung::A000000231589 | [5월 올영픽][대용량] 제로이드 수딩 크림  | 제로이드 | 건성 | 0.3704 |
| 8 | oliveyoung::A000000177758 | [추가증정] 넘버즈인 토너패드 증정 기획 중  | 넘버즈인 | 건성 | 0.3704 |
| 9 | oliveyoung::A000000225573 | [파데프리/톤업] 조선미녀 데일리 틴티드 선세 | 조선미녀 | 건성 | 0.3636 |
| 10 | oliveyoung::A000000148023 | [추가증정/저자극] 닥터지 약산성 클렌징 젤  | 닥터지 | 건성 | 0.3600 |
| 11 | oliveyoung::A000000252917 | [온라인단독] 라로슈포제 시카플라스트 밤 B5 | 라로슈포제 | 지성 | 0.3514 |
| 12 | oliveyoung::A000000149179 | 메디힐 티트리 임팩트인 밸런싱 마스크 1매 | 메디힐 | 복합성 | 0.3500 |
| 13 | oliveyoung::A000000012609 | 아이소이 에센셜 마스크팩 1매 3종 택 1 ( | 아이소이 | 건성 | 0.3478 |
| 14 | oliveyoung::A000000226515 | [포켓몬에디션]브링그린 징크테카 트러블세럼(대 | 브링그린 | 복합성 | 0.3478 |
| 15 | oliveyoung::A000000157350 | [트러블모공] 디오디너리 나이아신아마이드 10 | 디오디너리 | 건성 | 0.3478 |
| 16 | oliveyoung::A000000187480 | [여배우PICK] 바이오던스 바이오 콜라겐 리 | 바이오던스 | 지성 | 0.3404 |
| 17 | oliveyoung::A000000189181 | [수부지토너]브링그린 티트리 시카 수딩 토너  | 브링그린 | 건성 | 0.3333 |
| 18 | oliveyoung::A000000219609 | [대용량/트러블1등] 파티온 노스카나인 트러블 | 파티온 | 지성 | 0.3226 |
| 19 | oliveyoung::A000000248829 | [트러블 스케일링] 이옴 트러블 패치 마스크  | 이옴 | 지성 | 0.3200 |
| 20 | oliveyoung::A000000204081 | [오선우pick/파데프리] 아누아 매트벗글로우 | 아누아 | 지성 | 0.3200 |


    ---

    ## 5. 품질 검증 결과

    | 검증 항목 | 결과 | 판단 |
    |----------|------|------|
    | (product_key, base_skin_type) 중복 | 0 | OK |
    | base_skin_type null | 0 | OK |
    | skin_review_count <= 0 | 0 | OK |
    | skin count 합계 불일치 | 0 | OK |
    | overall count 합계 불일치 | 0 | OK |
    | skin rate 합계 최대 편차 | 1.11e-16 | OK |
    | overall rate 합계 최대 편차 | 1.11e-16 | OK |
    | parquet 재로드 row 수 일치 | 6008 == 6008 | OK |

    ---

    ## 6. 서비스 관점 판단

    ### Step 4 추천 점수 계산 가능 여부
    - 집계 수치 검증 통과 → Step 4 진행 가능

    ### 추천 점수에 사용할 수 있는 컬럼
    - `skin_negative_rate`, `skin_review_count`, `skin_confidence_label`
    - `overall_negative_rate`, `total_review_count`, `avg_rating`

    ### 부정 리뷰 우선 탐색에 사용할 수 있는 컬럼
    - `caution_level`, `caution_message`
    - `skin_negative_count`, `skin_negative_rate`

    ### 근거 부족 상품 처리 방식
    - `caution_level == insufficient_evidence` (skin_review_count < 5): 점수 산정 불가로 처리하거나 하위 표시

    ### 주의해야 할 모델 한계
    - predicted_sentiment는 BiLSTM v3 예측값 (macro_f1 0.666, neutral recall 0.586)
    - neutral 예측 신뢰도가 낮음 → neutral을 긍정/부정으로 잘못 분류할 가능성 존재
    - C09/C10/C11/C12/C13 skin_concern_code 의미 미확인 → UI 직접 노출 금지

    ---

    ## 수동 샘플 검수 결과

    - 직접 확인한 샘플 수: 271개 (aggregate_count_check 20 + high_negative_signal 30 + insufficient_evidence 20 + normal 20 + base_skin_type×5 각 20 + platform×2 각 20 + skin_need_tag 20 + skin_concern_tag 20 + coupang_absence 1)
    - 확인한 파일: reports/product_skin_aggregates_manual_review_samples.csv
    - 샘플링 그룹: aggregate_count_check / high_negative_signal / insufficient_evidence / normal / base_skin_type × 5 / platform × 2 / skin_need_tag / skin_concern_tag / coupang_absence_check

    ### aggregate count 검증 결과
    - 20개 (product_key + base_skin_type 조합) 전수 검증: **20/20 일치**
    - service_reviews 원본 재필터 집계와 product_skin_aggregates 집계값 (skin_review_count, skin_positive_count, skin_neutral_count, skin_negative_count) 완전 일치 확인

    ### high negative signal 샘플 판단
    - **총 20개 review_text 직접 확인** (service_reviews.parquet에서 product_key + base_skin_type별 negative review 조회)
    - 결과: **16/20 실제 부정 리뷰, 4/20 애매하거나 오분류 의심**

    #### 실제 부정 리뷰 확인 예시 (16개)
    - "너무너무 따가워요 바를때마다 맨날 간지럽고 따가워서... 민감성피부 절대사지마 절대로!!!!!!" (지성, neg_rate=0.320)
    - "피부염 나서 바디미스트로 썼는데 평생 나본적 없는 바디 트러블 났어요" (민감성, neg_rate=0.600)
    - "지성+민감성인데 얼굴에 홍조랑 열감 때문에 샀어요. 도톰하게 올린 부분은 화농성 여드름 파티구요" (건성, neg_rate=0.333)
    - "최악의 제품 걍 모공에서 피지가 나올 생각을 안 해여" (복합성, neg_rate=0.294)
    - "실패.. 너무 건조해요 극지성이라면 마음에 들겠지만 수부지는 너무 건조해서 사용 중단" (건성, neg_rate=0.250)
    - "이거 쓰고 얼굴에 뭐 엄청 올라왔어요.. 민감성이시고 홍조피부이신 분들 완저 ㄴ 비추" (복합성, neg_rate=0.261)
    - "이거 쓰고 피부 다 뒤집어지고 장벽 다 무너져서 지금까지 고생중임" (복합성, neg_rate=0.333)

    #### 애매하거나 오분류 의심 케이스 (4개)
    1. **명확한 오분류**: neg_rate=0.500, n=6, bst=민감성
       - review_text: "하 개비싼데 너무 빨리 써버리네..큰 얼굴을 탓해야하나 세일 자주해주세념ㅜㅜ 장벽 무너졌울때 이거만 바르면 3일안에 복구가능"
       - 판단: 실제 긍정 리뷰 (용량 아쉬움 + 효과 칭찬). n=6 소규모라 오류 1건이 neg_rate=0.500으로 부풀어짐
    2. **혼재형 부정**: 건성 / 구달 어성초 선크림 (neg_rate=0.333, n=18)
       - "톤업기능 좋아요, 발림성 잘 발립니다" + "화장할 때 밀림/벗겨짐" — 긍정·부정 혼재, 전반적으로는 부정
    3. **경계 케이스**: 건성 / 넘버즈인 클렌저 (neg_rate=0.267, n=15)
       - "클렌징이 약한 편, 자극" + "유화는 잘 되는 편" — 불만이지만 완전 부정은 아님
    4. **오분류 의심**: 지성 / 스트라이덱스 패드 (neg_rate=0.283, n=46)
       - "각질제거엔 요만한게없는거같아요", "맛들여서 순한제품 밍숭해서 못쓰겠어요" — 이 제품이 너무 강해서 다른 제품 못 쓴다는 역설적 긍정, 모델이 부정 어휘(따갑다)에 반응한 듯

    ### insufficient evidence 샘플 판단
    - 20개 확인: skin_review_count 분포 {1: 2건, 2: 6건, 3: 6건, 4: 6건}
    - **모두 0~4건 확인** — caution_level 분류 정확

    ### platform 샘플 판단
    - musinsa 20개, oliveyoung 20개 확인: 집계값 정상
    - **coupang: product_skin_aggregates row 수 = 0 (정상)** — base_skin_type 없는 coupang은 피부 타입 집계에서 올바르게 제외됨
    - platform_coupang_absence_check 항목에서 명시적으로 확인

    ### skin_need_tag / skin_concern_tag 샘플 판단
    - skin_need_tag_samples: 진정, 보습, 모공, 유수분 조절, 트러블 등 실제 skin_type 필드에서 나온 정상 값 확인
    - skin_concern_tag_samples: 주름, 미백, 홍조, 트러블, 보습 등 oliveyoung skin_concern 필드에서 나온 정상 값 확인

    ### 정상으로 판단한 예시
    - 어반쉐이드 쿨카밍 선스틱 / 복합성: top_skin_need_tags=[진정, 보습, 모공, 유수분 조절, 트러블] — 집계 정상
    - 아토베리어365 크림 / 복합성: skin_review_count=2410, neg_rate=0.024 — 대표 상품 정상 집계

    ### 이상하거나 애매한 예시
    - **neg_rate=1.0 그룹 (4-3 테이블 상위)**: skin_review_count가 1~2건인 경우가 다수 — n이 너무 적어 의미 없는 100% 부정률. insufficient_evidence (< 5건) 기준으로 올바르게 처리됨.
    - **중성 피부 타입**: avg_skin_review_count=2.1, insufficient_evidence=460/490 (93.9%). 리뷰가 극히 드물어 대부분 근거 부족 — Step 4에서 별도 처리 필요.
    - **high_negative_signal 중 4/20 애매·오분류**: 소규모 그룹(n < 10)에서 모델 오류 1건이 neg_rate에 큰 영향. 혼재형 리뷰(긍정·부정 공존)는 모델이 부정 어휘에 반응해 negative로 판단하는 경향 있음.

    ### 수정한 규칙
    - 없음. 기존 분류 기준 그대로 유효.

    ### 아직 남은 위험
    - BiLSTM 모델 오류 (macro_f1 0.666): 소규모 그룹(n < 10)에서 오류 1건이 neg_rate에 큰 영향 — 수동 검수에서 20개 중 4개(20%) 애매·오분류 확인
    - 중성 피부 타입 대부분 insufficient_evidence → Step 4에서 별도 처리 필요
    - 혼재형 리뷰(장단점 공존)는 모델이 부정 어휘에 과반응하는 경향 → neg_rate 단독 사용 주의

    ### Step 4 진행 가능 여부
    - **가능**
    - 집계 수치 검증 전부 통과, 수동 검수 20개에서 16/20 실제 부정 신호 확인
    - Step 4 주의 사항:
      - skin_review_count 최소 기준 엄격 적용 (≥ 20 권장, 최소 ≥ 5)
      - high_negative_signal 단독으로 "위험 상품" 단정 금지 — 근거 리뷰 수 충분성(confidence_label) 함께 제시
      - 중성 피부 타입 처리 방식 별도 결정 필요 (insufficient_evidence 93.9%)
