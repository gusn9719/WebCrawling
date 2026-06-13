"""올리브영 리뷰 전처리 패키지.

수업(0526) 네이버 영화 리뷰 RNN 감성분석 흐름을 베이스로,
올리브영 리뷰(JSONL)에 맞춰 확장한 전처리 파이프라인.

흐름:
    io.load_reviews            JSONL → DataFrame
        ↓
    cleaning.clean             결측·중복·정제·길이 필터
        ↓
    labeling.label_by_rating_and_text
                                별점 후보 라벨 + 본문 감성 단서
        ↓
    tokenize.tokenize          Okt 형태소 분석 + 불용어 제거
        ↓
    split.train_val            stratified 8:2

진입점은 패키지 한 단계 위의 run_preprocess.py.
크롤러처럼 단일 책임을 지키고, 모듈 간에는 config 만 공유한다.
"""
