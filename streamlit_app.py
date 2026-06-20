"""올리브영 리뷰 기반 감성 분석 Streamlit 서비스 — 리뷰핏."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ─────────────────────────────────────────────
# 경로 설정
# ─────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "preprocessed"
MODEL_DIR = BASE_DIR / "models"
REPORT_DIR = BASE_DIR / "reports"

# clf.classes_ = [0, 1, 2] → negative=0, neutral=1, positive=2
_ID2LABEL = {0: "negative", 1: "neutral", 2: "positive"}

# ─────────────────────────────────────────────
# KoNLPy 가용성 (모듈 레벨 — import 비용 한 번)
# ─────────────────────────────────────────────
_okt = None
_okt_available = False
try:
    from konlpy.tag import Okt  # type: ignore

    _okt = Okt()
    _okt_available = True
except Exception:
    pass

_HANGUL_ONLY = re.compile(r"[^ 가-힣]+")


def tokenize_input(text: str) -> str:
    """실시간 입력 토큰화. KoNLPy 없으면 한글+공백 기반 간단 처리."""
    cleaned = _HANGUL_ONLY.sub(" ", text.strip())
    cleaned = re.sub(r" +", " ", cleaned).strip()
    if _okt_available and _okt is not None:
        tokens = _okt.morphs(cleaned, stem=True)
        return " ".join(tokens)
    return " ".join(cleaned.split())


# ─────────────────────────────────────────────
# 모델 로드 (세션 공유 — 객체이므로 cache_resource)
# ─────────────────────────────────────────────
@st.cache_resource
def load_models():
    import joblib

    vec_path = MODEL_DIR / "tfidf_vectorizer.joblib"
    clf_path = MODEL_DIR / "baseline_logreg_balanced.joblib"

    if not vec_path.exists() or not clf_path.exists():
        st.error("모델 파일을 찾을 수 없습니다. models/ 폴더를 확인해 주세요.")
        st.stop()

    vec = joblib.load(vec_path)
    clf = joblib.load(clf_path)
    return vec, clf


# ─────────────────────────────────────────────
# 데이터 로드 + 집계 (직렬화 가능 — cache_data)
# ─────────────────────────────────────────────
@st.cache_data(show_spinner="분석 중... 첫 실행만 시간이 걸립니다")
def load_and_aggregate():
    import joblib

    vec = joblib.load(MODEL_DIR / "tfidf_vectorizer.joblib")
    clf = joblib.load(MODEL_DIR / "baseline_logreg_balanced.joblib")

    train = pd.read_parquet(DATA_DIR / "train.parquet")
    val = pd.read_parquet(DATA_DIR / "val.parquet")
    df = pd.concat([train, val], ignore_index=True)

    # clf.classes_ = [0, 1, 2] → 정수 예측 → 문자열 레이블로 변환
    pred_ids = clf.predict(vec.transform(df["tokens_str"].fillna("").astype(str)))
    df["pred_label"] = [_ID2LABEL[p] for p in pred_ids]

    grp = df.groupby("product_id")

    meta = grp.agg(
        product_name=("product_name", "first"),
        brand=("brand", "first"),
        category=("category", "first"),
        price=("price", "first"),
        review_count=("review_id", "count"),
        avg_rating=("rating", "mean"),
        product_url=("raw_url", "first"),
    ).reset_index()

    meta["positive_rate"] = (
        grp["pred_label"].apply(lambda x: (x == "positive").mean()).values
    )
    meta["negative_rate"] = (
        grp["pred_label"].apply(lambda x: (x == "negative").mean()).values
    )
    meta["neutral_rate"] = (
        grp["pred_label"].apply(lambda x: (x == "neutral").mean()).values
    )

    meta["positive_count"] = (meta["positive_rate"] * meta["review_count"]).round().astype(int)
    meta["negative_count"] = (meta["negative_rate"] * meta["review_count"]).round().astype(int)
    meta["neutral_count"] = (meta["neutral_rate"] * meta["review_count"]).round().astype(int)

    log_max = np.log1p(meta["review_count"].max())
    meta["score"] = (
        meta["positive_rate"] * 0.6
        + (meta["avg_rating"] / 5.0) * 0.3
        + np.log1p(meta["review_count"]) / log_max * 0.1
    ) * 100

    return meta, df


# ─────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────
def get_reviews(df: pd.DataFrame, product_id, label: str, n: int = 3) -> list[str]:
    """pred_label 기준 대표 리뷰. 20~300자, helpful_count 내림차순."""
    sub = df[
        (df["product_id"] == product_id) & (df["pred_label"] == label)
    ].copy()
    sub = sub[sub["clean_review"].str.len().between(20, 300)]
    if "helpful_count" in sub.columns:
        sub = sub.sort_values("helpful_count", ascending=False)
    return sub["clean_review"].head(n).tolist()


def apply_filters(
    stats: pd.DataFrame,
    cat: str,
    brands: list,
    price_max: int,
    include_high: bool,
    min_reviews: int,
    max_neg: float,
) -> pd.DataFrame:
    f = stats.copy()
    if cat != "전체":
        f = f[f["category"] == cat]
    if brands:
        f = f[f["brand"].isin(brands)]
    if not include_high:
        f = f[f["price"] <= 200_000]
    f = f[f["price"] <= price_max]
    f = f[f["review_count"] >= min_reviews]
    f = f[f["negative_rate"] <= max_neg]
    return f


# ─────────────────────────────────────────────
# 페이지 설정
# ─────────────────────────────────────────────
st.set_page_config(page_title="🌿 리뷰핏", layout="wide")
st.title("🌿 리뷰핏 — 올리브영 리뷰 감성 분석")

# ─────────────────────────────────────────────
# 데이터·모델 초기화
# ─────────────────────────────────────────────
load_models()
stats, full_df = load_and_aggregate()

# ─────────────────────────────────────────────
# 사이드바 필터
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 필터")

    cat_options = ["전체"] + sorted(stats["category"].dropna().unique().tolist())
    sel_cat = st.selectbox("카테고리", cat_options)

    brand_pool = (
        stats["brand"].dropna().unique().tolist()
        if sel_cat == "전체"
        else stats[stats["category"] == sel_cat]["brand"].dropna().unique().tolist()
    )
    sel_brands = st.multiselect("브랜드", sorted(brand_pool), placeholder="전체 브랜드")

    price_ceiling = min(int(stats["price"].max()), 200_000)
    price_max_val = st.slider("가격 상한", 0, price_ceiling, price_ceiling, step=1_000, format="%,d원")
    include_high = st.checkbox("20만원 초과 상품 포함", value=False)

    min_reviews = st.slider("최소 리뷰 수", 1, 300, 10)
    max_neg_pct = st.slider("최대 부정률 (%)", 0, 50, 50)
    max_neg = max_neg_pct / 100.0

    st.divider()
    st.caption("💡 피부타입·피부고민 필터는 비교 탭에서 제공합니다")

# ─────────────────────────────────────────────
# 탭 구성
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(
    ["🏆 상품 추천", "⚖️ 상품 비교", "📊 모델·데이터 리포트", "🔬 리뷰 직접 분석"]
)

# ═══════════════════════════════════════════════════════════════
# 탭 1: 상품 추천
# ═══════════════════════════════════════════════════════════════
with tab1:
    filtered = apply_filters(
        stats, sel_cat, sel_brands, price_max_val, include_high, min_reviews, max_neg
    )

    st.subheader(f"추천 상품 ({len(filtered):,}개)")

    if filtered.empty:
        st.info("필터 조건에 맞는 상품이 없습니다")
    else:
        col_sort, col_n = st.columns([2, 1])
        with col_sort:
            sort_by = st.selectbox(
                "정렬 기준",
                ["추천점수", "긍정률", "평균별점", "리뷰수"],
                key="tab1_sort",
            )
        with col_n:
            top_n = st.selectbox("표시 개수", [10, 20, 50], key="tab1_topn")

        sort_col = {
            "추천점수": "score",
            "긍정률": "positive_rate",
            "평균별점": "avg_rating",
            "리뷰수": "review_count",
        }[sort_by]

        ranked = (
            filtered.sort_values(sort_col, ascending=False)
            .head(top_n)
            .reset_index(drop=True)
        )

        display_df = pd.DataFrame(
            {
                "상품명": ranked["product_name"],
                "브랜드": ranked["brand"],
                "카테고리": ranked["category"],
                "가격(원)": ranked["price"].apply(
                    lambda v: f"{int(v):,}" if pd.notna(v) else "-"
                ),
                "리뷰수": ranked["review_count"],
                "평균별점": ranked["avg_rating"].apply(lambda v: f"{v:.2f}/5.0"),
                "긍정률": ranked["positive_rate"].apply(lambda v: f"{v*100:.1f}%"),
                "부정률": ranked["negative_rate"].apply(lambda v: f"{v*100:.1f}%"),
                "추천점수": ranked["score"].apply(lambda v: f"{v:.1f}"),
            }
        )
        display_df.index = display_df.index + 1
        st.dataframe(display_df, use_container_width=True, height=400)

        st.divider()

        sel_name = st.selectbox(
            "상세 보기", ranked["product_name"].tolist(), key="tab1_detail"
        )
        sel_row = ranked[ranked["product_name"] == sel_name].iloc[0]
        pid = sel_row["product_id"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("추천점수", f"{sel_row['score']:.1f}/100")
        c2.metric("평균별점", f"{sel_row['avg_rating']:.2f}/5.0")
        c3.metric("긍정률", f"{sel_row['positive_rate']*100:.1f}%")
        c4.metric("부정률", f"{sel_row['negative_rate']*100:.1f}%")

        col_pos, col_neg = st.columns(2)
        with col_pos:
            st.markdown("**😊 긍정 리뷰**")
            for r in get_reviews(full_df, pid, "positive", 3) or ["(없음)"]:
                if r == "(없음)":
                    st.caption(r)
                else:
                    st.info(r)

        with col_neg:
            st.markdown("**😞 부정 리뷰**")
            for r in get_reviews(full_df, pid, "negative", 3) or ["(없음)"]:
                if r == "(없음)":
                    st.caption(r)
                else:
                    st.warning(r)

        raw_url = sel_row.get("product_url")
        if raw_url and pd.notna(raw_url):
            st.link_button("🔗 올리브영 상품 페이지", str(raw_url))

        st.caption(
            "추천점수 = 긍정률×0.6 + 별점/5×0.3 + log(리뷰수) 정규화×0.1 — 참고용 지표"
        )

# ═══════════════════════════════════════════════════════════════
# 탭 2: 상품 비교
# ═══════════════════════════════════════════════════════════════
with tab2:
    st.subheader("상품 비교 (2~3개 선택)")

    product_options = stats.sort_values("score", ascending=False)["product_name"].tolist()
    sel_compare = st.multiselect(
        "비교할 상품",
        product_options,
        max_selections=3,
        placeholder="상품명을 검색하거나 선택",
    )

    if len(sel_compare) < 2:
        st.info("2개 이상 선택하면 비교가 시작됩니다")
    else:
        compare_rows = stats[stats["product_name"].isin(sel_compare)].copy()

        # 기본 지표 테이블
        tbl = compare_rows[
            [
                "product_name", "brand", "category", "price", "review_count",
                "avg_rating", "positive_rate", "negative_rate", "score",
            ]
        ].copy()
        tbl.columns = [
            "상품명", "브랜드", "카테고리", "가격(원)", "리뷰수",
            "평균별점", "긍정률", "부정률", "추천점수",
        ]
        tbl["가격(원)"] = tbl["가격(원)"].apply(
            lambda v: f"{int(v):,}" if pd.notna(v) else "-"
        )
        tbl["평균별점"] = tbl["평균별점"].apply(lambda v: f"{v:.2f}")
        tbl["긍정률"] = tbl["긍정률"].apply(lambda v: f"{v*100:.1f}%")
        tbl["부정률"] = tbl["부정률"].apply(lambda v: f"{v*100:.1f}%")
        tbl["추천점수"] = tbl["추천점수"].apply(lambda v: f"{v:.1f}")
        st.dataframe(tbl.set_index("상품명"), use_container_width=True)

        # 감성 분포 stacked bar
        chart_data = []
        for _, row in compare_rows.iterrows():
            chart_data += [
                {"상품명": row["product_name"], "감성": "긍정",        "비율": row["positive_rate"] * 100},
                {"상품명": row["product_name"], "감성": "부정",        "비율": row["negative_rate"] * 100},
                {"상품명": row["product_name"], "감성": "기타(불확실)", "비율": row["neutral_rate"] * 100},
            ]
        chart_df = pd.DataFrame(chart_data)

        fig_bar = px.bar(
            chart_df,
            x="상품명",
            y="비율",
            color="감성",
            barmode="stack",
            color_discrete_map={
                "긍정": "#4CAF50",
                "부정": "#F44336",
                "기타(불확실)": "#9E9E9E",
            },
            labels={"비율": "비율 (%)"},
            title="감성 분포 비교",
        )
        st.plotly_chart(fig_bar, use_container_width=True)
        st.caption("기타(불확실): neutral 예측 — precision 0.20 수준으로 신뢰도 낮음")

        # 피부타입별 긍정률 pivot
        if "skin_type" in full_df.columns:
            skin_sub = full_df[
                full_df["product_id"].isin(compare_rows["product_id"])
                & full_df["skin_type"].notna()
            ].merge(
                compare_rows[["product_id", "product_name"]], on="product_id", how="left"
            )
            if not skin_sub.empty:
                skin_sub["is_positive"] = (skin_sub["pred_label"] == "positive").astype(float)
                pivot = skin_sub.pivot_table(
                    index="skin_type",
                    columns="product_name",
                    values="is_positive",
                    aggfunc="mean",
                )
                pivot = (pivot * 100).round(1)
                st.markdown("**피부타입별 긍정률 (%)**")
                st.dataframe(pivot, use_container_width=True)
                st.caption(
                    "피부타입 정보가 있는 리뷰는 전체의 약 42%입니다 — 참고용으로만 활용하세요"
                )
            else:
                st.info("피부타입 정보 없음")

        # 대표 리뷰 비교
        st.divider()
        st.markdown("**대표 리뷰 비교**")
        for _, row in compare_rows.iterrows():
            with st.expander(f"📝 {row['product_name']}"):
                rc1, rc2 = st.columns(2)
                with rc1:
                    st.markdown("😊 **긍정 리뷰**")
                    pos_revs = get_reviews(full_df, row["product_id"], "positive", 2)
                    for r in pos_revs or ["(없음)"]:
                        (st.info if r != "(없음)" else st.caption)(r)
                with rc2:
                    st.markdown("😞 **부정 리뷰**")
                    neg_revs = get_reviews(full_df, row["product_id"], "negative", 2)
                    for r in neg_revs or ["(없음)"]:
                        (st.warning if r != "(없음)" else st.caption)(r)
                url = row.get("product_url")
                if url and pd.notna(url):
                    st.link_button("🔗 올리브영 상품 페이지", str(url))

# ═══════════════════════════════════════════════════════════════
# 탭 3: 모델·데이터 리포트
# ═══════════════════════════════════════════════════════════════
with tab3:
    # 섹션 1: 데이터 개요
    with st.expander("📦 데이터 개요", expanded=True):
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 리뷰 수", f"{len(full_df):,}")
        m2.metric("고유 상품 수", f"{full_df['product_id'].nunique():,}")
        m3.metric("카테고리 수", f"{full_df['category'].nunique()}")
        if "review_date" in full_df.columns:
            dates = pd.to_datetime(full_df["review_date"], errors="coerce")
            m4.metric(
                "수집 기간",
                f"{dates.min().strftime('%Y-%m-%d')} ~ {dates.max().strftime('%Y-%m-%d')}",
            )

        cat_cnt = full_df.groupby("category").size().reset_index(name="리뷰수")
        fig_cat = px.bar(
            cat_cnt,
            x="category",
            y="리뷰수",
            color="category",
            title="카테고리별 리뷰 수",
            labels={"category": "카테고리"},
        )
        st.plotly_chart(fig_cat, use_container_width=True)

        # 원본 라벨 분포 (sentiment_label 컬럼)
        label_col = "sentiment_label" if "sentiment_label" in full_df.columns else "pred_label"
        label_cnt = full_df[label_col].value_counts().reset_index()
        label_cnt.columns = ["감성", "건수"]
        label_cnt["감성"] = label_cnt["감성"].replace({"neutral": "기타(neutral)"})
        fig_pie = px.pie(
            label_cnt,
            names="감성",
            values="건수",
            title="감성 라벨 분포",
            color="감성",
            color_discrete_map={
                "positive": "#4CAF50",
                "negative": "#F44336",
                "기타(neutral)": "#9E9E9E",
            },
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    # 섹션 2: 모델 성능 비교
    with st.expander("🤖 모델 성능 비교", expanded=True):
        metric_files = sorted(REPORT_DIR.glob("*_metrics.json"))
        model_rows = []
        for mf in metric_files:
            with open(mf, encoding="utf-8") as f:
                m = json.load(f)
            cm = m.get("class_metrics", {})
            model_rows.append(
                {
                    "모델": mf.stem.replace("_metrics", ""),
                    "Accuracy": round(m.get("accuracy", 0), 4),
                    "Macro F1": round(m.get("macro_f1", 0), 4),
                    "Positive F1": round(cm.get("positive", {}).get("f1", 0), 4),
                    "Negative F1": round(cm.get("negative", {}).get("f1", 0), 4),
                    "Neutral F1": round(cm.get("neutral", {}).get("f1", 0), 4),
                    "Neutral Precision": round(cm.get("neutral", {}).get("precision", 0), 4),
                }
            )
        model_df = pd.DataFrame(model_rows)
        st.dataframe(model_df, use_container_width=True)
        st.warning(
            "⚠️ **Neutral 클래스 주의**\n\n"
            "baseline_balanced 기준 neutral precision = 0.20\n\n"
            "→ 모델이 'neutral'로 예측한 것의 80%가 실제로 positive 또는 negative입니다.\n\n"
            "이 서비스에서 '기타/불확실'로 표시하는 이유입니다."
        )

    # 섹션 3: LSTM 학습 이력
    with st.expander("📈 LSTM 학습 이력"):
        hist_path = REPORT_DIR / "lstm_balanced_e3_earlystop_history.csv"
        if hist_path.exists():
            hist = pd.read_csv(hist_path)
            hist.insert(0, "epoch", range(1, len(hist) + 1))

            fig_loss = px.line(
                hist,
                x="epoch",
                y=["loss", "val_loss"],
                title="Loss 추이",
                labels={"value": "Loss", "variable": "구분"},
            )
            st.plotly_chart(fig_loss, use_container_width=True)

            fig_acc = px.line(
                hist,
                x="epoch",
                y=["accuracy", "val_accuracy"],
                title="Accuracy 추이",
                labels={"value": "Accuracy", "variable": "구분"},
            )
            st.plotly_chart(fig_acc, use_container_width=True)
        else:
            st.info("LSTM 학습 이력 파일을 찾을 수 없습니다.")

# ═══════════════════════════════════════════════════════════════
# 탭 4: 리뷰 직접 분석
# ═══════════════════════════════════════════════════════════════
with tab4:
    if not _okt_available:
        st.info("KoNLPy를 불러올 수 없어 공백 기반 분석 모드로 동작합니다.")

    if "input_text" not in st.session_state:
        st.session_state["input_text"] = ""

    col_b1, col_b2, col_b3 = st.columns(3)
    if col_b1.button("긍정 예시"):
        st.session_state["input_text"] = (
            "보습력이 정말 좋아요. 피부가 촉촉해지고 다음에도 살 것 같아요"
        )
    if col_b2.button("부정 예시"):
        st.session_state["input_text"] = (
            "향이 너무 강하고 자극적이에요. 환불하고 싶어요"
        )
    if col_b3.button("중립 예시"):
        st.session_state["input_text"] = (
            "그냥 평범해요. 특별히 좋거나 나쁜 점은 없는 것 같아요"
        )

    user_text = st.text_area(
        "리뷰 문장 입력",
        value=st.session_state["input_text"],
        height=100,
        key="user_input_area",
    )

    if st.button("분석하기", type="primary"):
        if not user_text.strip():
            st.warning("텍스트를 입력해주세요.")
        else:
            vec, clf = load_models()
            tokenized = tokenize_input(user_text)
            proba = clf.predict_proba(vec.transform([tokenized]))[0]
            # clf.classes_ = [0, 1, 2]: negative=0, neutral=1, positive=2
            prob = {_ID2LABEL[c]: p for c, p in zip(clf.classes_, proba)}
            pos_p = prob.get("positive", 0.0)
            neg_p = prob.get("negative", 0.0)
            neu_p = prob.get("neutral", 0.0)

            st.markdown("#### 분석 결과")
            st.markdown("**😊 긍정**")
            st.progress(pos_p, text=f"{pos_p*100:.1f}%")
            st.markdown("**😞 부정**")
            st.progress(neg_p, text=f"{neg_p*100:.1f}%")
            st.markdown(f"**😐 기타(불확실)**: {neu_p*100:.1f}%")
            st.caption("⚠️ neutral(기타) 예측은 신뢰도가 낮습니다 (F1=0.28, precision=0.20)")

            if pos_p >= 0.6:
                st.success("✅ 긍정적인 리뷰로 분류됩니다.")
            elif neg_p >= 0.4:
                st.error("⚠️ 부정적인 내용을 포함하는 리뷰입니다.")
            else:
                st.info("ℹ️ 긍정/부정 판정이 불확실한 리뷰입니다.")

            tokens_preview = tokenized.split()[:20]
            st.markdown(f"**사용된 토큰 (앞 20개):** `{' '.join(tokens_preview)}`")
            st.caption(
                "KoNLPy Okt 형태소 분석 사용"
                if _okt_available
                else "공백 기반 간단 분석 모드"
            )
