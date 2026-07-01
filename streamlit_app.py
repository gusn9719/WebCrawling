"""화장품 리뷰 기반 피부타입 맞춤 부정 신호 확인 Streamlit 서비스."""

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
DATA_DIR = BASE_DIR / "preprocessed_v3"
MODEL_DIR = BASE_DIR / "models"
REPORT_DIR = BASE_DIR / "reports"
SCORES_PARQUET = DATA_DIR / "product_recommendation_scores.parquet"

_ID2LABEL = {0: "negative", 1: "neutral", 2: "positive"}

MODEL_OPTIONS: dict[str, str] = {
    "베이스라인 (TF-IDF)":     "baseline",
    "LSTM (BiLSTM)":           "lstm_v3",
    "Transformer (KLUE-BERT)": "transformer_v3",
}
PLATFORM_OPTIONS = ["전체", "oliveyoung", "musinsa", "coupang"]
PLATFORM_KR = {
    "oliveyoung": "올리브영",
    "musinsa":    "무신사",
    "coupang":    "쿠팡",
    "전체":       "전체",
}

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
_BRACKET_PREFIX = re.compile(r"^(\[.*?\]\s*)+")
_PAREN_SUFFIX = re.compile(r"\s*\(.*\)\s*$")


def shorten_name(name: str, max_len: int = 35) -> str:
    name = _BRACKET_PREFIX.sub("", name).strip()
    name = _PAREN_SUFFIX.sub("", name).strip()
    return name if len(name) <= max_len else name[:max_len] + "…"


def tokenize_input(text: str) -> str:
    """실시간 입력 토큰화. KoNLPy 없으면 한글+공백 기반 간단 처리."""
    cleaned = _HANGUL_ONLY.sub(" ", text.strip())
    cleaned = re.sub(r" +", " ", cleaned).strip()
    if _okt_available and _okt is not None:
        tokens = _okt.morphs(cleaned, stem=True)
        return " ".join(tokens)
    return " ".join(cleaned.split())


# ─────────────────────────────────────────────
# 모델 로딩 (세션 공유 — 객체이므로 cache_resource)
# ─────────────────────────────────────────────
@st.cache_resource
def load_baseline():
    import joblib

    vec = joblib.load(MODEL_DIR / "tfidf_vectorizer.joblib")
    clf = joblib.load(MODEL_DIR / "baseline_logreg_balanced.joblib")
    return vec, clf


@st.cache_resource(show_spinner="LSTM v3 모델 로딩 중...")
def load_lstm_v3():
    import tensorflow as tf  # type: ignore

    return tf.keras.models.load_model(MODEL_DIR / "lstm_final_v3.keras")


@st.cache_resource(
    show_spinner="Transformer (KLUE-BERT) 로딩 중... 첫 실행에만 30~60초 소요됩니다"
)
def load_transformer_v3():
    from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore

    path = str(MODEL_DIR / "transformer_final_v3")
    tokenizer = AutoTokenizer.from_pretrained(path)
    model = AutoModelForSequenceClassification.from_pretrained(path)
    model.eval()
    return tokenizer, model


# ─────────────────────────────────────────────
# 배치 추론 (Tab 1/2 집계용)
# ─────────────────────────────────────────────
def predict_proba_batch(texts_series: pd.Series, model_key: str) -> np.ndarray:
    """Returns shape (N, 3) — columns: [negative=0, neutral=1, positive=2]."""
    texts = texts_series.fillna("").astype(str)
    if model_key == "baseline":
        vec, clf = load_baseline()
        return clf.predict_proba(vec.transform(texts))
    elif model_key == "lstm_v3":
        model = load_lstm_v3()
        # numpy object dtype은 Keras TextVectorization이 거부 → tf.string 명시 변환
        import tensorflow as tf  # type: ignore
        texts_tf = tf.constant(texts.tolist(), dtype=tf.string)
        texts_tf = tf.reshape(texts_tf, (-1, 1))
        return model.predict(texts_tf, batch_size=1024, verbose=0)
    else:
        raise ValueError(f"배치 추론에 지원하지 않는 모델: {model_key}")


# ─────────────────────────────────────────────
# 단일 추론 (Tab 4 전용)
# ─────────────────────────────────────────────
def predict_single(text: str, model_key: str) -> dict[str, float]:
    """세 모델 모두 지원. 반환: {'negative': p, 'neutral': p, 'positive': p}"""
    tokenized = tokenize_input(text)
    if model_key == "baseline":
        vec, clf = load_baseline()
        proba = clf.predict_proba(vec.transform([tokenized]))[0]
        return {_ID2LABEL[c]: float(p) for c, p in zip(clf.classes_, proba)}
    elif model_key == "lstm_v3":
        model = load_lstm_v3()
        import tensorflow as tf  # type: ignore
        texts_tf = tf.constant([[tokenized]], dtype=tf.string)
        proba = model.predict(texts_tf, verbose=0)[0]
        return {_ID2LABEL[i]: float(p) for i, p in enumerate(proba)}
    else:  # transformer_v3
        import torch  # type: ignore

        tok, mdl = load_transformer_v3()
        inputs = tok(text, return_tensors="pt", truncation=True, max_length=128)
        with torch.no_grad():
            logits = mdl(**inputs).logits
        proba = torch.softmax(logits, dim=-1)[0].tolist()
        return {_ID2LABEL[i]: float(p) for i, p in enumerate(proba)}


def render_result(result: dict[str, float]) -> None:
    """예측 확률 프로그레스바 + neutral 경고. 세 모델 공통 출력 형식."""
    st.progress(result["positive"], text=f"😊 긍정 {result['positive']*100:.1f}%")
    st.progress(result["negative"], text=f"😞 부정 {result['negative']*100:.1f}%")
    st.markdown(f"😐 불확실: {result['neutral']*100:.1f}%")

    pred = max(result, key=result.get)  # type: ignore[arg-type]
    if pred == "neutral":
        st.caption("😐 판단이 어려운 경계 리뷰입니다. 직접 읽고 확인하세요.")
    elif result["positive"] >= 0.6:
        st.success("✅ 긍정적인 리뷰로 분류됩니다.")
    elif result["negative"] >= 0.4:
        st.warning("모델이 부정 신호를 감지했습니다. 실제 의미는 리뷰 본문을 함께 확인하세요.")
    else:
        st.info("ℹ️ 긍정/부정 판정이 불확실한 리뷰입니다.")


# ─────────────────────────────────────────────
# 데이터 로드 + 집계 (직렬화 가능 — cache_data)
# ─────────────────────────────────────────────
_LSTM_PREDS_PATH = DATA_DIR / "lstm_v3_preds.parquet"
_TRANSFORMER_PREDS_PATH = DATA_DIR / "transformer_v3_preds.parquet"

_PRED_COL = {
    "lstm_v3":        ("lstm_v3_pred",        _LSTM_PREDS_PATH),
    "transformer_v3": ("transformer_v3_pred", _TRANSFORMER_PREDS_PATH),
}


@st.cache_data(show_spinner="데이터 집계 중... 첫 실행만 시간이 걸립니다")
def load_and_aggregate(model_key: str):
    # 플랫폼 필터를 캐시 키에서 제거 — 모델 변경 시만 parquet 재로딩,
    # 플랫폼 전환은 apply_filters()에서 in-memory 처리
    train_path = DATA_DIR / "train.parquet"
    val_path = DATA_DIR / "val.parquet"
    if not train_path.exists() or not val_path.exists():
        _meta_cols = [
            "product_id", "product_name", "brand", "category", "price",
            "platform", "review_count", "avg_rating", "raw_url",
            "positive_rate", "negative_rate", "neutral_rate",
            "positive_count", "negative_count", "neutral_count", "score",
        ]
        _full_cols = [
            "product_id", "product_name", "brand", "category", "price",
            "platform", "review_id", "rating", "review_text", "clean_review",
            "tokens_str", "sentiment_label", "skin_type", "helpful_count",
            "raw_url", "pred_label",
        ]
        return pd.DataFrame(columns=_meta_cols), pd.DataFrame(columns=_full_cols)
    train = pd.read_parquet(train_path)
    val = pd.read_parquet(val_path)
    df = pd.concat([train, val], ignore_index=True)

    pred_col, pred_path = _PRED_COL.get(model_key, (None, None))

    if pred_col is not None and pred_path is not None and pred_path.exists():
        preds_df = pd.read_parquet(pred_path)
        df = df.merge(preds_df, on="review_id", how="left")
        df["pred_label"] = df[pred_col].fillna("positive")
    else:
        effective_key = "lstm_v3" if model_key == "transformer_v3" else model_key
        proba = predict_proba_batch(df["tokens_str"], effective_key)
        df["pred_label"] = [_ID2LABEL[p] for p in proba.argmax(axis=1)]

    grp = df.groupby("product_id")
    meta = grp.agg(
        product_name=("product_name", "first"),
        brand=("brand", "first"),
        category=("category", "first"),
        price=("price", "first"),
        platform=("platform", "first"),
        review_count=("review_id", "count"),
        avg_rating=("rating", "mean"),
        raw_url=("raw_url", "first"),
    ).reset_index()

    rates = (
        grp["pred_label"]
        .value_counts(normalize=True)
        .unstack(fill_value=0)
        .reindex(columns=["positive", "negative", "neutral"], fill_value=0)
    )
    meta["positive_rate"] = rates["positive"].values
    meta["negative_rate"] = rates["negative"].values
    meta["neutral_rate"] = rates["neutral"].values

    # 크롤러 버그로 product_name이 literal "nan"인 상품 제거
    meta = meta[meta["product_name"].str.strip().ne("nan") & meta["product_name"].str.strip().ne("")]

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
    sub = df[(df["product_id"] == product_id) & (df["pred_label"] == label)]
    sub = sub[sub["clean_review"].str.len().between(20, 300)]
    if "helpful_count" in sub.columns:
        sub = sub.sort_values("helpful_count", ascending=False)
    return sub["clean_review"].head(n).tolist()


def get_reviews_with_rating(
    df: pd.DataFrame,
    product_id,
    label: str,
    n: int = 3,
) -> list[tuple[str, float | None]]:
    sub = df[(df["product_id"] == product_id) & (df["pred_label"] == label)]
    sub = sub[sub["clean_review"].str.len().between(20, 300)]
    if "helpful_count" in sub.columns:
        sub = sub.sort_values("helpful_count", ascending=False)
    result: list[tuple[str, float | None]] = []
    for _, _row in sub.head(n).iterrows():
        _text = _row["clean_review"]
        _rat = float(_row["rating"]) if "rating" in sub.columns and pd.notna(_row.get("rating")) else None
        result.append((_text, _rat))
    return result


def apply_filters(
    stats: pd.DataFrame,
    platform_filter: str,
    cat: str,
    brands: list,
    price_max: int,
    include_high: bool,
    min_reviews: int,
    max_neg: float,
) -> pd.DataFrame:
    f = stats
    if platform_filter != "전체":
        f = f[f["platform"] == platform_filter]
    if cat != "전체":
        f = f[f["category"] == cat]
    if brands:
        f = f[f["brand"].isin(brands)]
    # NaN 가격(쿠팡)은 가격 조건을 적용하지 않고 그대로 통과
    if not include_high:
        price_ok = f["price"].isna() | (f["price"] <= 200_000)
        f = f[price_ok]
    price_ok = f["price"].isna() | (f["price"] <= price_max)
    f = f[price_ok]
    f = f[f["review_count"] >= min_reviews]
    f = f[f["negative_rate"] <= max_neg]
    return f


# ─────────────────────────────────────────────
# 피부타입 맞춤 추천 — 데이터 로딩
# ─────────────────────────────────────────────
@st.cache_data(show_spinner="피부타입 추천 데이터 로딩 중...")
def load_personalized_recommendation_data():
    if not SCORES_PARQUET.exists():
        st.error(f"피부타입 추천 점수 파일을 찾을 수 없습니다: {SCORES_PARQUET}")
        st.stop()
    score_df = pd.read_parquet(SCORES_PARQUET)
    if len(score_df) != 6008:
        st.warning(f"피부타입 추천 점수 행 수가 예상과 다릅니다: {len(score_df)} (예상: 6008)")
    required_score_cols = [
        "product_key", "base_skin_type", "recommendation_score",
        "evidence_level", "rank_exposure_flag", "review_first_flag", "display_message",
    ]
    missing = [c for c in required_score_cols if c not in score_df.columns]
    if missing:
        st.error(f"product_recommendation_scores.parquet 필수 컬럼 누락: {missing}")
        st.stop()

    _SVC_REQUIRED = ["product_key", "base_skin_type", "predicted_sentiment", "review_text"]
    _SVC_OPTIONAL = ["clean_review", "rating", "helpful_count", "platform", "skin_type", "skin_concern"]
    svc_path = DATA_DIR / "service_reviews.parquet"
    if not svc_path.exists():
        return score_df, None
    try:
        service_df = pd.read_parquet(svc_path, columns=_SVC_REQUIRED + _SVC_OPTIONAL)
    except Exception:
        try:
            service_df = pd.read_parquet(svc_path, columns=_SVC_REQUIRED)
        except Exception as e:
            st.error(f"service_reviews 필수 컬럼 로딩 실패: {e}")
            st.stop()
    if len(service_df) != 402438:
        st.warning(f"service_reviews 행 수가 예상과 다릅니다: {len(service_df)} (예상: 402438)")
    return score_df, service_df


# ─────────────────────────────────────────────
# 피부타입 맞춤 추천 — 필터
# ─────────────────────────────────────────────
def filter_personalized_scores(
    score_df: pd.DataFrame,
    selected_skin_type: str,
    platform_filter: str,
    category_filter: str,
    brand_filter: list,
    price_max: int,
    include_insufficient: bool,
    include_review_first: bool,
    min_skin_reviews: int,
    max_skin_negative_rate: float,
    only_rank_exposure: bool,
    sort_by: str,
) -> pd.DataFrame:
    f = score_df[score_df["base_skin_type"] == selected_skin_type].copy()
    if platform_filter != "전체":
        f = f[f["platform"] == platform_filter]
    if category_filter != "전체":
        f = f[f["category"] == category_filter]
    if brand_filter:
        f = f[f["brand"].isin(brand_filter)]
    if "price" in f.columns:
        price_ok = f["price"].isna() | (f["price"] <= price_max)
        f = f[price_ok]
    if "skin_review_count" in f.columns:
        f = f[f["skin_review_count"] >= min_skin_reviews]
    if "skin_negative_rate" in f.columns:
        f = f[f["skin_negative_rate"] <= max_skin_negative_rate]
    if not include_insufficient:
        f = f[f["evidence_level"] != "insufficient_evidence"]
    if not include_review_first and "caution_level" in f.columns:
        f = f[~f["caution_level"].isin(["high_negative_signal", "moderate_negative_signal"])]
    if only_rank_exposure:
        f = f[f["rank_exposure_flag"] == True]  # noqa: E712
    sort_map = {
        "검토 점수": ("recommendation_score", False),
        "피부타입 리뷰 수": ("skin_review_count", False),
        "피부타입 부정률 낮은순": ("skin_negative_rate", True),
        "평균별점": ("avg_rating", False),
        "전체 부정률 낮은순": ("overall_negative_rate", True),
    }
    if sort_by in sort_map:
        col, asc = sort_map[sort_by]
        if col in f.columns:
            f = f.sort_values(col, ascending=asc)
    return f.reset_index(drop=True)


# ─────────────────────────────────────────────
# 피부타입 맞춤 추천 — 리뷰 조회 헬퍼
# ─────────────────────────────────────────────
def get_skin_reviews(
    service_df: pd.DataFrame,
    product_key: str,
    base_skin_type: str,
    label: str,
    n: int = 5,
) -> pd.DataFrame:
    mask = (
        (service_df["product_key"] == product_key)
        & (service_df["base_skin_type"] == base_skin_type)
        & (service_df["predicted_sentiment"] == label)
    )
    sub = service_df[mask].copy()
    if sub.empty:
        return sub
    if "clean_review" in sub.columns:
        sub["_text"] = sub["clean_review"].fillna("").str.strip()
        empty_mask = sub["_text"].str.len() < 20
        if "review_text" in sub.columns:
            sub.loc[empty_mask, "_text"] = sub.loc[empty_mask, "review_text"].fillna("").str.strip()
    else:
        sub["_text"] = sub["review_text"].fillna("").str.strip()
    sub = sub[sub["_text"].str.len() >= 20]
    if sub.empty:
        return sub
    if "helpful_count" in sub.columns:
        sub = sub.sort_values("helpful_count", ascending=False, na_position="last")
    return_cols = ["_text"]
    for c in ["rating", "helpful_count", "platform", "skin_type", "skin_concern", "predicted_sentiment"]:
        if c in sub.columns:
            return_cols.append(c)
    return sub[return_cols].head(n).reset_index(drop=True)


def get_product_reviews(
    service_df: pd.DataFrame,
    product_key: str,
    label: str | None = None,
    max_rating: int | None = None,
    n: int = 5,
) -> pd.DataFrame:
    mask = service_df["product_key"] == product_key
    if label is not None:
        mask = mask & (service_df["predicted_sentiment"] == label)
    if max_rating is not None and "rating" in service_df.columns:
        mask = mask & (service_df["rating"] <= max_rating)
    sub = service_df[mask].copy()
    if sub.empty:
        return sub
    if "clean_review" in sub.columns:
        sub["_text"] = sub["clean_review"].fillna("").str.strip()
        empty_mask = sub["_text"].str.len() < 20
        if "review_text" in sub.columns:
            sub.loc[empty_mask, "_text"] = sub.loc[empty_mask, "review_text"].fillna("").str.strip()
    else:
        sub["_text"] = sub["review_text"].fillna("").str.strip()
    sub = sub[sub["_text"].str.len() >= 20]
    if sub.empty:
        return sub
    if "helpful_count" in sub.columns:
        sub = sub.sort_values("helpful_count", ascending=False, na_position="last")
    return_cols = ["_text"]
    for c in ["rating", "helpful_count", "platform", "skin_type", "skin_concern", "predicted_sentiment"]:
        if c in sub.columns:
            return_cols.append(c)
    return sub[return_cols].head(n).reset_index(drop=True)


def _get_review_count(row: pd.Series, service_df: pd.DataFrame, label: str) -> int:
    col_map = {
        "negative": "skin_negative_count",
        "positive": "skin_positive_count",
        "neutral": "skin_neutral_count",
    }
    col = col_map.get(label)
    if col and col in row.index and pd.notna(row[col]):
        return int(row[col])
    mask = (
        (service_df["product_key"] == row["product_key"])
        & (service_df["base_skin_type"] == row["base_skin_type"])
        & (service_df["predicted_sentiment"] == label)
    )
    return int(mask.sum())


def _render_review_card(r: pd.Series) -> None:
    text = str(r["_text"])
    display_text = text[:200] + "..." if len(text) > 200 else text
    st.markdown(f"> {display_text}")
    meta_parts = []
    if "rating" in r.index and pd.notna(r["rating"]):
        meta_parts.append(f"별점: {r['rating']}점")
    if "helpful_count" in r.index and pd.notna(r.get("helpful_count")) and r.get("helpful_count", 0) > 0:
        meta_parts.append(f"도움됨: {int(r['helpful_count'])}명")
    if meta_parts:
        st.caption(" / ".join(meta_parts))
    st.divider()


def _on_sidebar_platform_change() -> None:
    st.session_state["sidebar_category"] = "전체"
    st.session_state["sidebar_brands"]   = []
    st.session_state["skin_cat"]         = "전체"
    st.session_state["skin_brand"]       = []
    st.session_state["tab2_compare_products"] = []

def _on_sidebar_category_change() -> None:
    st.session_state["sidebar_brands"] = []

def _on_skin_cat_change() -> None:
    st.session_state["skin_brand"] = []


def _reset_skin_filters() -> None:
    st.session_state["skin_cat"]         = "전체"
    st.session_state["skin_brand"]       = []
    st.session_state["skin_price"]       = 200_000
    st.session_state["skin_min_rev"]     = 1
    st.session_state["skin_max_neg"]     = 100
    st.session_state["skin_incl_insuff"] = False
    st.session_state["skin_incl_rf"]     = True
    st.session_state["skin_rank_exp"]    = True
    st.session_state["skin_sort"]        = "피부타입 리뷰 수"


def _render_skin_product_detail(row: pd.Series, service_df: pd.DataFrame | None) -> None:
    _EVIDENCE_KO = {
        "strong_evidence":       "충분한 근거 (20건+)",
        "limited_evidence":      "제한된 근거 (5-19건)",
        "insufficient_evidence": "근거 부족 (5건 미만)",
    }
    _TIER_KO = {
        "strong_candidate":      "추천 검토 가능",
        "review_before_buying":  "리뷰 확인 권장",
        "insufficient_evidence": "근거 부족",
        "caution_check":         "부정 신호 확인",
        "negative_review_first": "부정 리뷰 우선 확인",
    }

    st.subheader(str(row["product_name"]))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("검토 점수", f"{row['recommendation_score']:.1f}")
    c2.metric("피부타입 리뷰 수", int(row["skin_review_count"]))
    c3.metric("피부타입 부정률", f"{row['skin_negative_rate']:.1%}")
    c4.metric("평균별점", f"{row['avg_rating']:.1f}" if pd.notna(row["avg_rating"]) else "-")

    c5, c6, c7 = st.columns(3)
    _onr = row.get("overall_negative_rate")
    c5.metric("전체 부정률", f"{_onr:.1%}" if pd.notna(_onr) else "-")
    c6.metric("근거 수준", _EVIDENCE_KO.get(str(row["evidence_level"]), str(row["evidence_level"])))
    c7.metric("검토 등급", _TIER_KO.get(str(row["recommendation_tier"]), str(row["recommendation_tier"])))

    if row["review_first_flag"]:
        st.warning(
            "이 상품은 선택 피부 타입 리뷰에서 부정 신호가 확인되어, "
            "구매 전 부정 리뷰를 먼저 확인하는 것을 권장합니다."
        )
    if row["evidence_level"] == "insufficient_evidence":
        st.info("선택 피부 타입 리뷰 수가 적어 결과를 참고용으로만 확인하세요.")
    if row["base_skin_type"] == "중성":
        st.info(
            "중성 피부 타입은 전체적으로 리뷰 근거가 적은 편입니다. "
            "점수보다 실제 리뷰 본문을 함께 확인하세요."
        )

    _msg = str(row.get("display_message", ""))
    if _msg and _msg not in ("nan", "None", ""):
        st.info(_msg)

    raw_url = row.get("raw_url")
    if service_df is None:
        st.info(
            "리뷰 본문을 표시하려면 service_reviews.parquet가 필요합니다.  \n"
            "GitHub Releases에서 다운로드 후 preprocessed_v3/ 폴더에 배치하세요."
        )
        if raw_url and pd.notna(raw_url):
            st.link_button("상품 페이지 바로가기", str(raw_url))
        return

    negative_count = _get_review_count(row, service_df, "negative")
    positive_count = _get_review_count(row, service_df, "positive")
    neutral_count  = _get_review_count(row, service_df, "neutral")

    _pk  = str(row["product_key"])
    _bst = str(row["base_skin_type"])

    _skin_neg_cnt = negative_count
    _all_neg_mask = (
        (service_df["product_key"] == _pk)
        & (service_df["predicted_sentiment"] == "negative")
    )
    _all_neg_cnt = int(_all_neg_mask.sum())
    _low_rate_cnt: int | str = "-"
    if "rating" in service_df.columns:
        _low_rate_cnt = int(
            ((service_df["product_key"] == _pk) & (service_df["rating"] <= 3)).sum()
        )

    st.caption(
        f"리뷰 조회 기준: 선택 피부타입 부정 예측 {_skin_neg_cnt}건 / "
        f"전체 상품 부정 예측 {_all_neg_cnt}건 / "
        f"낮은 별점 리뷰 {_low_rate_cnt}건"
    )

    _neg_skin = get_skin_reviews(service_df, _pk, _bst, "negative", n=5)

    if not _neg_skin.empty:
        st.markdown("#### 선택 피부타입 부정 리뷰 먼저 보기")
        for _, _rv in _neg_skin.iterrows():
            _render_review_card(_rv)
    else:
        _neg_all = get_product_reviews(service_df, _pk, label="negative", n=5)
        if not _neg_all.empty:
            st.info(
                "선택 피부 타입 기준으로 모델이 부정으로 예측한 리뷰는 없습니다.  \n"
                "대신 같은 상품의 전체 부정 리뷰를 참고용으로 보여줍니다."
            )
            st.markdown("#### 전체 상품 부정 리뷰 참고")
            for _, _rv in _neg_all.iterrows():
                _render_review_card(_rv)
        else:
            _low_rev = get_product_reviews(service_df, _pk, max_rating=3, n=5)
            if not _low_rev.empty:
                st.info(
                    "모델이 부정으로 예측한 리뷰는 찾지 못했습니다.  \n"
                    "대신 같은 상품의 낮은 별점 리뷰를 참고용으로 보여줍니다."
                )
                st.markdown("#### 낮은 별점 리뷰 참고")
                for _, _rv in _low_rev.iterrows():
                    _render_review_card(_rv)
            else:
                st.info(
                    "현재 조건에서 표시할 부정 또는 낮은 별점 리뷰를 찾지 못했습니다.  \n"
                    "이 경우에도 검토 점수와 리뷰 수는 참고용으로만 확인하세요."
                )

    st.caption("리뷰 감성은 BiLSTM 모델 예측값(참고용)이며 실제 감성과 다를 수 있습니다.")

    with st.expander(f"선택 피부타입 긍정 리뷰 ({positive_count}건)"):
        pos_reviews = get_skin_reviews(
            service_df, str(row["product_key"]), str(row["base_skin_type"]), "positive", n=5
        )
        if pos_reviews.empty:
            st.caption("표시할 긍정 리뷰가 없습니다.")
        else:
            for _, rv in pos_reviews.iterrows():
                _render_review_card(rv)

    with st.expander(f"참고용 기타 리뷰 ({neutral_count}건, 중립)"):
        neu_reviews = get_skin_reviews(
            service_df, str(row["product_key"]), str(row["base_skin_type"]), "neutral", n=3
        )
        if neu_reviews.empty:
            st.caption("표시할 중립 리뷰가 없습니다.")
        else:
            for _, rv in neu_reviews.iterrows():
                _render_review_card(rv)

    raw_url = row.get("raw_url")
    if raw_url and pd.notna(raw_url):
        st.link_button("상품 페이지 바로가기", str(raw_url))


# ─────────────────────────────────────────────
# 페이지 설정
# ─────────────────────────────────────────────
st.set_page_config(page_title="🌿 리뷰핏", layout="wide")
st.title("🌿 리뷰핏 — 멀티 플랫폼 리뷰 감성 분석")

# ─────────────────────────────────────────────
# 사이드바
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("모델")

    _model_labels = list(MODEL_OPTIONS.keys())
    _default_model_idx = _model_labels.index("LSTM (BiLSTM)") if "LSTM (BiLSTM)" in _model_labels else 0
    sel_model_label = st.selectbox("분석 모델", _model_labels, index=_default_model_idx)
    sel_model = MODEL_OPTIONS[sel_model_label]

    if sel_model in ("lstm_v3", "transformer_v3"):
        _, preds_path = _PRED_COL[sel_model]
        if not preds_path.exists():
            st.caption("⚠️ 첫 집계 시 분석 시간이 소요됩니다.")

    st.divider()
    st.header("플랫폼")

    sel_platform = st.radio(
        "플랫폼 선택",
        PLATFORM_OPTIONS,
        format_func=lambda x: PLATFORM_KR.get(x, x),
        label_visibility="collapsed",
        key="sidebar_platform",
        on_change=_on_sidebar_platform_change,
    )

# 데이터 집계 (model_key만 캐시 키 — 플랫폼 전환은 apply_filters에서 처리)
stats, full_df = load_and_aggregate(sel_model)

with st.sidebar:
    st.divider()
    with st.expander("상세 필터", expanded=True):
        # platform 기준으로 category 후보 계산
        if sel_platform == "전체":
            _cat_src = stats
        else:
            _cat_src = stats[stats["platform"] == sel_platform]
        cat_options = ["전체"] + sorted(_cat_src["category"].dropna().unique().tolist())

        if st.session_state.get("sidebar_category", "전체") not in cat_options:
            st.session_state["sidebar_category"] = "전체"

        sel_cat = st.selectbox(
            "카테고리",
            cat_options,
            key="sidebar_category",
            on_change=_on_sidebar_category_change,
        )

        # platform + category 기준으로 brand 후보 계산
        _brand_src = stats if sel_platform == "전체" else stats[stats["platform"] == sel_platform]
        if sel_cat != "전체":
            _brand_src = _brand_src[_brand_src["category"] == sel_cat]
        brand_pool = sorted(_brand_src["brand"].dropna().unique().tolist())

        _valid_sidebar_brands = [b for b in st.session_state.get("sidebar_brands", []) if b in brand_pool]
        if _valid_sidebar_brands != st.session_state.get("sidebar_brands", []):
            st.session_state["sidebar_brands"] = _valid_sidebar_brands

        sel_brands = st.multiselect(
            "브랜드",
            brand_pool,
            key="sidebar_brands",
            placeholder="전체 브랜드",
        )

        include_high = st.checkbox("20만원 초과 상품 포함", value=False, key="sidebar_include_high")
        _valid_prices = stats["price"].dropna()
        _abs_max = int(_valid_prices.max()) if len(_valid_prices) > 0 else 200_000
        price_ceiling = _abs_max if include_high else min(_abs_max, 200_000)
        price_max_val = st.slider("가격 상한", 0, price_ceiling, price_ceiling, step=1_000, format="%,d원", key="sidebar_price_max")

        min_reviews = st.slider("최소 리뷰 수", 1, 300, 10, key="sidebar_min_reviews")
        max_neg_pct = st.slider("최대 부정률 (%)", 0, 50, 50, key="sidebar_max_neg_pct")
        max_neg = max_neg_pct / 100.0

# ─────────────────────────────────────────────
# 탭 구성
# ─────────────────────────────────────────────
tab_skin, tab1, tab2, tab3, tab4 = st.tabs([
    "피부타입 맞춤 추천",
    "일반 상품 추천",
    "상품 비교",
    "모델·데이터 리포트",
    "리뷰 직접 분석",
])

# ═══════════════════════════════════════════════════════════════
# 탭 0: 피부타입 맞춤 추천
# ═══════════════════════════════════════════════════════════════
with tab_skin:
    score_df_skin, service_df_skin = load_personalized_recommendation_data()

    # [1] 3단계 사용 흐름 안내
    st.markdown(
        "사용 방법:  \n"
        "1단계. 피부 타입 선택  \n"
        "2단계. 조건 확인 (기본값으로 바로 사용 가능)  \n"
        "3단계. 상품 선택 후 부정 리뷰 먼저 확인"
    )

    # [2] info 배너 간소화
    st.info(
        "같은 피부 타입 사용자의 리뷰를 기반으로 부정 신호를 먼저 확인합니다. "
        "BiLSTM 모델 예측 기반 참고 지표이며, 구매 전 리뷰 본문을 함께 확인하세요."
    )

    if sel_platform == "coupang":
        st.warning(
            "Coupang 데이터에는 피부 타입 정보가 없어 피부타입 맞춤 추천을 제공할 수 없습니다. "
            "사이드바에서 전체 또는 oliveyoung / musinsa를 선택해 주세요."
        )
    else:
        _plat_label = "oliveyoung + musinsa" if sel_platform == "전체" else sel_platform
        st.caption(f"현재 적용 플랫폼: {_plat_label}")

        col_skin_type, col_skin_note = st.columns([2, 4])
        with col_skin_type:
            selected_skin_type = st.radio(
                "피부 타입 선택",
                ["지성", "건성", "민감성", "복합성", "중성"],
                horizontal=True,
                key="skin_type_radio",
            )
        with col_skin_note:
            if selected_skin_type == "중성":
                st.warning(
                    "중성 피부는 리뷰 근거가 적은 상품이 많습니다. "
                    "고급 필터에서 '추천 노출 후보만' 해제 + '근거 부족 포함' 활성화를 권장합니다."
                )

        # [4] 기본 필터 — expander 없이 2열 표시
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if sel_platform == "전체":
                _sco_src = score_df_skin
            else:
                _sco_src = score_df_skin[score_df_skin["platform"] == sel_platform]
            skin_cat_opts = ["전체"] + sorted(_sco_src["category"].dropna().unique().tolist())
            if st.session_state.get("skin_cat", "전체") not in skin_cat_opts:
                st.session_state["skin_cat"] = "전체"
            skin_cat = st.selectbox(
                "카테고리",
                skin_cat_opts,
                key="skin_cat",
                on_change=_on_skin_cat_change,
            )
        with col_b2:
            skin_sort = st.selectbox(
                "정렬 기준",
                ["피부타입 리뷰 수", "검토 점수", "피부타입 부정률 낮은순", "평균별점", "전체 부정률 낮은순"],
                key="skin_sort",
            )

        # [4][5][6] 고급 필터 — expander (expanded=False)
        with st.expander("고급 필터", expanded=False):
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                # [5] 브랜드: sidebar platform + 피부타입·카테고리 기준으로 범위 축소
                _brand_base = score_df_skin if sel_platform == "전체" else score_df_skin[score_df_skin["platform"] == sel_platform]
                _brand_base = _brand_base[_brand_base["base_skin_type"] == selected_skin_type]
                if skin_cat != "전체":
                    _brand_base = _brand_base[_brand_base["category"] == skin_cat]
                brand_pool_skin = sorted(_brand_base["brand"].dropna().unique().tolist())
                _valid_skin_brands = [b for b in st.session_state.get("skin_brand", []) if b in brand_pool_skin]
                if _valid_skin_brands != st.session_state.get("skin_brand", []):
                    st.session_state["skin_brand"] = _valid_skin_brands
                skin_brands = st.multiselect(
                    "브랜드", brand_pool_skin, key="skin_brand", placeholder="미선택 시 전체"
                )
                price_max_skin = st.slider(
                    "가격 상한", 0, 200_000, 200_000, step=5_000, format="%,d원", key="skin_price"
                )
            with col_f2:
                min_skin_rev = st.slider("최소 피부타입 리뷰 수", 1, 50, 1, key="skin_min_rev")
                max_skin_neg_pct = st.slider(
                    "최대 피부타입 부정률 (%)", 0, 100, 100, step=5, key="skin_max_neg"
                )
            with col_f3:
                include_insuff = st.checkbox("근거 부족 상품 포함", value=False, key="skin_incl_insuff")
                include_rev_first = st.checkbox(
                    "부정 리뷰 먼저 확인 대상 포함", value=True, key="skin_incl_rf"
                )
                only_rank_exp = st.checkbox(
                    "추천 상위 노출 후보만 보기", value=True, key="skin_rank_exp"
                )
                # [6] 필터 초기화 — on_click 콜백 방식
                st.button("필터 초기화", on_click=_reset_skin_filters, key="skin_reset")

        # [7] 활성 필터 조건 요약
        _conds: list[str] = []
        if sel_platform != "전체":
            _conds.append(f"플랫폼: {sel_platform}")
        if skin_cat != "전체":
            _conds.append(f"카테고리: {skin_cat}")
        if skin_brands:
            _brand_str = ", ".join(skin_brands[:3]) + ("..." if len(skin_brands) > 3 else "")
            _conds.append(f"브랜드: {_brand_str}")
        if price_max_skin < 200_000:
            _conds.append(f"가격: ~{price_max_skin:,}원")
        if only_rank_exp:
            _conds.append("추천 노출 후보만")
        if not include_insuff:
            _conds.append("근거 부족 제외")
        st.caption("현재 조건: " + (" / ".join(_conds) if _conds else "없음 (전체)"))

        filtered_skin_df = filter_personalized_scores(
            score_df_skin,
            selected_skin_type,
            sel_platform,
            skin_cat,
            skin_brands,
            price_max_skin,
            include_insuff,
            include_rev_first,
            min_skin_rev,
            max_skin_neg_pct / 100.0,
            only_rank_exp,
            skin_sort,
        )

        sm1, sm2, sm3, sm4, sm5 = st.columns(5)
        sm1.metric("후보 상품 수", len(filtered_skin_df))
        sm2.metric(
            "추천 노출 가능",
            int(filtered_skin_df["rank_exposure_flag"].sum()) if len(filtered_skin_df) else 0,
        )
        sm3.metric(
            "부정 리뷰 먼저 확인",
            int(filtered_skin_df["review_first_flag"].sum()) if len(filtered_skin_df) else 0,
        )
        sm4.metric(
            "평균 피부타입 부정률",
            f"{filtered_skin_df['skin_negative_rate'].mean():.1%}" if len(filtered_skin_df) else "-",
        )
        # [8] 메트릭 라벨 한국어화
        sm5.metric(
            "충분한 근거",
            int((filtered_skin_df["evidence_level"] == "strong_evidence").sum())
            if len(filtered_skin_df) else 0,
        )

        # [9] 빈 상태 — 구체적 복구 힌트
        if filtered_skin_df.empty:
            _hints: list[str] = ["조건에 맞는 상품이 없습니다."]
            if only_rank_exp:
                _hints.append("'추천 노출 후보만' 체크를 해제하면 더 많은 상품이 표시됩니다.")
            if not include_insuff:
                _hints.append("'근거 부족 포함'을 켜면 리뷰가 적은 상품도 확인할 수 있습니다.")
            if selected_skin_type == "중성":
                _hints.append(
                    "중성 피부는 데이터 자체가 희소합니다. "
                    "'추천 노출 후보만'을 해제하고 '근거 부족 포함'을 켜서 확인하세요."
                )
            if skin_brands:
                _brand_str2 = ", ".join(skin_brands[:2])
                _hints.append(f"브랜드 필터({_brand_str2})를 해제하면 더 많은 상품이 표시됩니다.")
            st.info("  \n".join(_hints))
        else:
            _SKIN_RENAME = {
                "product_name": "상품명",
                "brand": "브랜드",
                "platform": "플랫폼",
                "category": "카테고리",
                "price": "가격",
                "skin_review_count": "피부타입 리뷰 수",
                "skin_negative_rate": "피부타입 부정률",
                "overall_negative_rate": "전체 부정률",
                "avg_rating": "평균별점",
                "recommendation_score": "검토 점수",
                "evidence_level": "근거 수준",
                "review_first_flag": "부정 리뷰 먼저 확인",
            }
            ranked_skin = filtered_skin_df.reset_index(drop=True)
            display_cols = [c for c in _SKIN_RENAME if c in ranked_skin.columns]
            display_skin_df = ranked_skin[display_cols].rename(columns=_SKIN_RENAME)

            table_event = st.dataframe(
                display_skin_df,
                width="stretch",
                height=400,
                on_select="rerun",
                selection_mode="single-row",
                key="skin_recommendation_table",
            )

            _select_options = ranked_skin["product_key"].tolist()
            _label_map: dict[str, str] = {}
            for _, _r in ranked_skin.iterrows():
                _pk = str(_r["product_key"])
                _name = str(_r.get("product_name", ""))[:28]
                _brand = str(_r.get("brand", ""))
                _plat = str(_r.get("platform", ""))
                _rev = int(_r.get("skin_review_count", 0))
                _score = float(_r.get("recommendation_score", 0.0))
                _label_map[_pk] = (
                    f"{_name} [{_brand} / {_plat}] 리뷰 {_rev}건 검토 점수 {_score:.1f}"
                )
            from collections import Counter as _Counter
            _label_counts = _Counter(_label_map.values())
            _dup_seq: dict[str, int] = {}
            for _pk2, _lbl in list(_label_map.items()):
                if _label_counts[_lbl] > 1:
                    _dup_seq[_lbl] = _dup_seq.get(_lbl, 0) + 1
                    _label_map[_pk2] = f"{_lbl} (동명 상품 {_dup_seq[_lbl]})"

            _selected_rows = table_event.selection.rows
            if _selected_rows:
                _sel_idx = _selected_rows[0]
                if 0 <= _sel_idx < len(ranked_skin):
                    st.session_state["skin_sel_prod"] = _select_options[_sel_idx]

            _cur_pk = st.session_state.get("skin_sel_prod")
            if _cur_pk not in _select_options:
                _cur_pk = _select_options[0]
                st.session_state["skin_sel_prod"] = _cur_pk
            _cur_idx = _select_options.index(_cur_pk)

            selected_product_key = st.selectbox(
                "상품 선택 (상세 보기)",
                _select_options,
                index=_cur_idx,
                format_func=lambda _k: _label_map.get(str(_k), "상품 정보 없음"),
                key="skin_sel_prod",
            )
            selected_skin_row = ranked_skin[
                ranked_skin["product_key"] == selected_product_key
            ].iloc[0]

            st.divider()
            _render_skin_product_detail(selected_skin_row, service_df_skin)

# ═══════════════════════════════════════════════════════════════
# 탭 1: 상품 추천
# ═══════════════════════════════════════════════════════════════
with tab1:
    filtered = apply_filters(
        stats, sel_platform, sel_cat, sel_brands, price_max_val, include_high, min_reviews, max_neg
    )

    st.subheader(f"추천 상품 ({len(filtered):,}개)")

    if stats.empty:
        st.info(
            "서비스 데이터 파일(train.parquet, val.parquet)이 없습니다.  \n"
            "GitHub Releases에서 파일을 다운로드한 후 preprocessed_v3/ 폴더에 배치하면 이 탭을 사용할 수 있습니다."
        )
    elif filtered.empty:
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
                "상품명":   ranked["product_name"].apply(shorten_name),
                "브랜드":   ranked["brand"].apply(lambda v: "정보 없음" if pd.isna(v) else v),
                "플랫폼":   ranked["platform"].apply(lambda x: PLATFORM_KR.get(x, x)),
                "카테고리": ranked["category"],
                "가격(원)": ranked["price"].apply(lambda v: f"{int(v):,}" if pd.notna(v) else "-"),
                "리뷰수":   ranked["review_count"],
                "평균별점": ranked["avg_rating"].apply(lambda v: f"{v:.2f}/5.0"),
                "긍정률":   ranked["positive_rate"].apply(lambda v: f"{v*100:.1f}%"),
                "부정률":   ranked["negative_rate"].apply(lambda v: f"{v*100:.1f}%"),
                "추천점수": ranked["score"].apply(lambda v: f"{v:.1f}"),
            }
        )
        display_df.index = display_df.index + 1
        st.caption("긍정률: 리뷰 중 긍정 비율 | 추천점수: 긍정률 60% + 별점 30% + 리뷰수 10% | 행을 클릭하면 아래에 상세 정보가 표시됩니다")
        table_event = st.dataframe(
            display_df,
            column_config={
                "상품명": st.column_config.TextColumn("상품명", help="클릭하여 상세 정보 보기"),
            },
            width="stretch",
            height=400,
            on_select="rerun",
            selection_mode="single-row",
        )

        st.divider()

        # 상품 선택: selectbox(상품명 클릭)가 기본, 표 왼쪽 체크박스도 동작
        selected_rows = table_event.selection.rows
        _product_names = ranked["product_name"].tolist()

        # selectbox로 선택하면 session_state에 저장, 표 체크박스 선택이 있으면 그걸 우선
        if selected_rows:
            _default_idx = selected_rows[0]
            # key가 있는 selectbox는 session_state가 index보다 우선 → 직접 업데이트
            st.session_state["tab1_product_selectbox"] = _product_names[_default_idx]
        elif "tab1_selected_product" in st.session_state and st.session_state["tab1_selected_product"] in _product_names:
            _default_idx = _product_names.index(st.session_state["tab1_selected_product"])
        else:
            _default_idx = None

        selected_name = st.selectbox(
            "상품 선택",
            _product_names,
            index=_default_idx,
            placeholder="상품명을 입력하거나 목록에서 선택",
            key="tab1_product_selectbox",
            label_visibility="collapsed",
        )

        if selected_name:
            st.session_state["tab1_selected_product"] = selected_name
            sel_row = ranked[ranked["product_name"] == selected_name].iloc[0]
            plat_kr = PLATFORM_KR.get(sel_row.get("platform", ""), "")
            pid = sel_row["product_id"]

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("추천점수", f"{sel_row['score']:.1f}/100")
            c2.metric("평균별점", f"{sel_row['avg_rating']:.2f}/5.0")
            c3.metric("긍정률",   f"{sel_row['positive_rate']*100:.1f}%")
            c4.metric("부정률",   f"{sel_row['negative_rate']*100:.1f}%")

            col_pos, col_neg = st.columns(2)
            with col_pos:
                st.markdown("**😊 긍정 리뷰**")
                pos_reviews = get_reviews(full_df, pid, "positive", 3)
                if pos_reviews:
                    for r in pos_reviews:
                        st.info(r)
                else:
                    st.caption("긍정 리뷰 없음")
            with col_neg:
                st.markdown("**모델 부정 감지 리뷰 참고**")
                _neg_with_rat = get_reviews_with_rating(full_df, pid, "negative", 3)
                if _neg_with_rat:
                    for _rtxt, _rrat in _neg_with_rat:
                        st.error(_rtxt)
                        if _rrat is not None:
                            if _rrat >= 4:
                                st.caption(
                                    f"별점: {_rrat:.0f}점 — "
                                    "모델은 부정 신호로 감지했지만 별점이 높은 리뷰입니다. "
                                    "문맥을 직접 확인하세요."
                                )
                            else:
                                st.caption(f"별점: {_rrat:.0f}점")
                else:
                    st.caption("모델이 부정으로 감지한 리뷰를 찾지 못했습니다.")

            raw_url = sel_row.get("raw_url")
            if raw_url and pd.notna(raw_url):
                st.link_button("🔗 상품 페이지", str(raw_url))
            elif sel_row.get("platform") == "coupang":
                st.caption("🛒 쿠팡 상품은 브랜드·가격·링크 정보를 제공하지 않습니다.")
        else:
            st.info("위 표에서 상품명을 선택하거나 행 왼쪽 체크박스를 클릭하면 상세 정보가 표시됩니다.")

# ═══════════════════════════════════════════════════════════════
# 탭 2: 상품 비교
# ═══════════════════════════════════════════════════════════════
with tab2:
    st.subheader("상품 비교 (2~3개 선택)")
    st.caption("서로 다른 플랫폼의 상품도 비교할 수 있습니다")

    if sel_platform == "전체":
        _compare_src = stats.copy()
    else:
        _compare_src = stats[stats["platform"] == sel_platform].copy()

    if "product_key" in _compare_src.columns:
        _compare_src["_compare_key"] = _compare_src["product_key"].astype(str)
    else:
        _compare_src["_compare_key"] = (
            _compare_src["platform"].astype(str) + "::" + _compare_src["product_id"].astype(str)
        )

    _compare_label_map: dict[str, str] = {}
    for _, _r in _compare_src.iterrows():
        _ck = str(_r["_compare_key"])
        _name = str(_r.get("product_name", ""))[:28]
        _brand = str(_r.get("brand", ""))
        _plat = str(_r.get("platform", ""))
        _compare_label_map[_ck] = f"{_name} [{_brand} / {_plat}]"

    _compare_keys_sorted = _compare_src.sort_values("score", ascending=False)["_compare_key"].tolist()

    sel_compare_keys = st.multiselect(
        "비교할 상품",
        _compare_keys_sorted,
        format_func=lambda _k: _compare_label_map.get(str(_k), "상품 정보 없음"),
        max_selections=3,
        placeholder="상품명을 검색하거나 선택",
        key="tab2_compare_products",
    )

    if len(sel_compare_keys) < 2:
        st.info("2개 이상 선택하면 비교가 시작됩니다")
    else:
        compare_rows = _compare_src[_compare_src["_compare_key"].isin(sel_compare_keys)].copy()

        tbl = compare_rows[
            [
                "product_name", "brand", "platform", "category", "price",
                "review_count", "avg_rating", "positive_rate", "negative_rate", "score",
            ]
        ].copy()
        tbl.columns = [
            "상품명", "브랜드", "플랫폼", "카테고리", "가격(원)",
            "리뷰수", "평균별점", "긍정률", "부정률", "추천점수",
        ]
        tbl["브랜드"]   = tbl["브랜드"].apply(lambda v: "정보 없음" if pd.isna(v) else v)
        tbl["플랫폼"]   = tbl["플랫폼"].apply(lambda x: PLATFORM_KR.get(x, x))
        tbl["가격(원)"] = tbl["가격(원)"].apply(lambda v: f"{int(v):,}" if pd.notna(v) else "-")
        tbl["평균별점"] = tbl["평균별점"].apply(lambda v: f"{v:.2f}")
        tbl["긍정률"]   = tbl["긍정률"].apply(lambda v: f"{v*100:.1f}%")
        tbl["부정률"]   = tbl["부정률"].apply(lambda v: f"{v*100:.1f}%")
        tbl["추천점수"] = tbl["추천점수"].apply(lambda v: f"{v:.1f}")
        st.dataframe(tbl.set_index("상품명"), width="stretch")

        chart_data = []
        for _, row in compare_rows.iterrows():
            plat_label = PLATFORM_KR.get(row.get("platform", ""), "")
            label = f"{shorten_name(row['product_name'], 18)} [{plat_label}]"
            chart_data += [
                {"상품명": label, "감성": "긍정",         "비율": row["positive_rate"] * 100},
                {"상품명": label, "감성": "부정",         "비율": row["negative_rate"] * 100},
                {"상품명": label, "감성": "기타(불확실)", "비율": row["neutral_rate"]  * 100},
            ]
        fig_bar = px.bar(
            pd.DataFrame(chart_data),
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
        st.plotly_chart(fig_bar, width="stretch")
        st.caption("불확실: 긍정/부정 경계로 판단이 어려운 리뷰")

        if "skin_type" in full_df.columns:
            skin_sub = full_df[
                full_df["product_id"].isin(compare_rows["product_id"])
                & full_df["skin_type"].notna()
            ].copy()
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
                st.dataframe(pivot, width="stretch")
                st.caption(
                    "피부타입 정보는 올리브영 데이터에 주로 포함됩니다 — 참고용으로만 활용하세요"
                )
            else:
                st.info("피부타입 정보 없음 (올리브영 상품을 포함해 비교해 보세요)")

        st.divider()
        st.markdown("**대표 리뷰 비교**")
        for _, row in compare_rows.iterrows():
            plat_kr = PLATFORM_KR.get(row.get("platform", ""), "")
            with st.expander(f"📝 {row['product_name']} [{plat_kr}]"):
                rc1, rc2 = st.columns(2)
                with rc1:
                    st.markdown("😊 **긍정 리뷰**")
                    pos_revs = get_reviews(full_df, row["product_id"], "positive", 2)
                    for r in pos_revs or ["(없음)"]:
                        (st.info if r != "(없음)" else st.caption)(r)
                with rc2:
                    st.markdown("**모델 부정 감지 리뷰 참고**")
                    _neg_revs_w_rat = get_reviews_with_rating(full_df, row["product_id"], "negative", 2)
                    if _neg_revs_w_rat:
                        for _rtxt, _rrat in _neg_revs_w_rat:
                            st.warning(_rtxt)
                            if _rrat is not None:
                                if _rrat >= 4:
                                    st.caption(
                                        f"별점: {_rrat:.0f}점 — 모델 부정 감지, 별점 높음. 문맥 확인 권장."
                                    )
                                else:
                                    st.caption(f"별점: {_rrat:.0f}점")
                    else:
                        st.caption("모델이 부정으로 감지한 리뷰를 찾지 못했습니다.")
                url = row.get("raw_url")
                if url and pd.notna(url):
                    st.link_button("🔗 상품 페이지", str(url))

# ═══════════════════════════════════════════════════════════════
# 탭 3: 모델·데이터 리포트
# ═══════════════════════════════════════════════════════════════
with tab3:
    with st.expander("📦 데이터 개요", expanded=True):
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 리뷰 수", f"{len(full_df):,}")
        m2.metric("고유 상품 수", f"{full_df['product_id'].nunique():,}")
        m3.metric("카테고리 수", f"{full_df['category'].nunique()}")
        if "review_date" in full_df.columns:
            dates = pd.to_datetime(full_df["review_date"], errors="coerce")
            if dates.notna().any():
                m4.metric(
                    "수집 기간",
                    f"{dates.min().strftime('%Y-%m-%d')} ~ {dates.max().strftime('%Y-%m-%d')}",
                )

        col_cat, col_plat = st.columns(2)
        with col_cat:
            cat_cnt = full_df.groupby("category").size().reset_index(name="리뷰수")
            fig_cat = px.bar(
                cat_cnt,
                x="category",
                y="리뷰수",
                color="category",
                title="카테고리별 리뷰 수",
                labels={"category": "카테고리"},
            )
            st.plotly_chart(fig_cat, width="stretch")
        with col_plat:
            plat_cnt = full_df.groupby("platform").size().reset_index(name="리뷰수")
            plat_cnt["플랫폼"] = plat_cnt["platform"].apply(lambda x: PLATFORM_KR.get(x, x))
            fig_plat = px.pie(
                plat_cnt,
                names="플랫폼",
                values="리뷰수",
                title="플랫폼별 리뷰 비중",
            )
            st.plotly_chart(fig_plat, width="stretch")

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
        st.plotly_chart(fig_pie, width="stretch")

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
        st.dataframe(model_df, width="stretch")
        st.warning(
            "⚠️ **Neutral 클래스 주의**\n\n"
            "세 모델 모두 Neutral F1 = 0.15~0.29 수준입니다.\n\n"
            "→ neutral로 예측될 경우 이 서비스는 '기타/불확실'로 표시하며 신뢰도 경고를 함께 보여줍니다."
        )

    with st.expander("📈 LSTM v3 학습 이력"):
        hist_path = REPORT_DIR / "lstm_final_v3_history.csv"
        if hist_path.exists():
            hist = pd.read_csv(hist_path)
            hist.insert(0, "epoch", range(1, len(hist) + 1))
            loss_cols = [c for c in ["loss", "val_loss"] if c in hist.columns]
            if loss_cols:
                fig_loss = px.line(
                    hist, x="epoch", y=loss_cols, title="LSTM v3 Loss 추이",
                    labels={"value": "Loss", "variable": "구분"},
                )
                st.plotly_chart(fig_loss, width="stretch")
            acc_cols = [c for c in ["accuracy", "val_accuracy"] if c in hist.columns]
            if acc_cols:
                fig_acc = px.line(
                    hist, x="epoch", y=acc_cols, title="LSTM v3 Accuracy 추이",
                    labels={"value": "Accuracy", "variable": "구분"},
                )
                st.plotly_chart(fig_acc, width="stretch")
        else:
            st.info("LSTM v3 학습 이력 파일을 찾을 수 없습니다 (reports/lstm_final_v3_history.csv).")

    with st.expander("📈 Transformer 학습 이력"):
        hist_path_tf = REPORT_DIR / "transformer_final_v3_history.csv"
        if hist_path_tf.exists():
            hist_tf = pd.read_csv(hist_path_tf)
            # history CSV에 train step 행과 eval 행이 interleaved — epoch 기준으로 분리 후 병합
            train_rows = hist_tf[hist_tf["loss"].notna()][["epoch", "loss"]].copy()
            eval_rows = hist_tf[hist_tf["eval_loss"].notna()][
                [c for c in ["epoch", "eval_loss", "eval_macro_f1"] if c in hist_tf.columns]
            ].copy()

            if not train_rows.empty and not eval_rows.empty:
                merged = pd.merge(train_rows, eval_rows, on="epoch", how="outer").sort_values("epoch")
                loss_cols_tf = [c for c in ["loss", "eval_loss"] if c in merged.columns]
                fig_loss_tf = px.line(
                    merged, x="epoch", y=loss_cols_tf, title="Transformer Loss 추이",
                    labels={"value": "Loss", "variable": "구분"},
                )
                st.plotly_chart(fig_loss_tf, width="stretch")
                if "eval_macro_f1" in merged.columns:
                    fig_f1_tf = px.line(
                        merged, x="epoch", y=["eval_macro_f1"],
                        title="Transformer Macro F1 추이 (eval)",
                        labels={"value": "F1", "variable": "구분"},
                    )
                    st.plotly_chart(fig_f1_tf, width="stretch")
            else:
                st.dataframe(hist_tf, width="stretch")
        else:
            st.info(
                "Transformer 학습 이력 파일을 찾을 수 없습니다 (reports/transformer_final_v3_history.csv)."
            )

    with st.expander("피부타입 맞춤 추천 데이터", expanded=False):
        try:
            _score_info_df, _ = load_personalized_recommendation_data()
            st.metric("총 행 수", len(_score_info_df))
            st.markdown("**base_skin_type 분포**")
            st.dataframe(_score_info_df["base_skin_type"].value_counts().reset_index())
            st.markdown("**evidence_level 분포**")
            st.dataframe(_score_info_df["evidence_level"].value_counts().reset_index())
            st.markdown("**recommendation_tier 분포**")
            st.dataframe(_score_info_df["recommendation_tier"].value_counts().reset_index())
            st.markdown("**rank_exposure_flag / review_first_flag**")
            st.write(f"rank_exposure_flag=True: {_score_info_df['rank_exposure_flag'].sum()}")
            st.write(f"review_first_flag=True: {_score_info_df['review_first_flag'].sum()}")
            st.caption(
                "쿠팡은 피부 타입 정보가 없어 제외됩니다. 중성 피부 타입은 리뷰 근거가 희소합니다."
            )
        except Exception as e:
            st.warning(f"피부타입 추천 데이터 로딩 실패: {e}")

# ═══════════════════════════════════════════════════════════════
# 탭 4: 리뷰 직접 분석
# ═══════════════════════════════════════════════════════════════
with tab4:
    if not _okt_available:
        st.info("KoNLPy를 불러올 수 없어 공백 기반 분석 모드로 동작합니다.")

    compare_mode = st.toggle("모델 비교 모드 (LSTM vs Transformer)")

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

    user_text = st.text_area("리뷰 문장 입력", height=100, key="input_text")

    if not user_text.strip():
        st.caption("텍스트를 입력하면 분석 버튼이 활성화됩니다.")

    if st.button("분석하기", type="primary", disabled=not user_text.strip()):
        if not user_text.strip():
            st.warning("텍스트를 입력해주세요.")
        elif compare_mode:
            st.markdown("#### 모델 비교 결과")
            col_lstm, col_tf = st.columns(2)
            with col_lstm:
                st.markdown("### LSTM")
                with st.spinner("LSTM 분석 중..."):
                    result_lstm = predict_single(user_text, "lstm_v3")
                render_result(result_lstm)
            with col_tf:
                st.markdown("### Transformer")
                with st.spinner("Transformer 분석 중... (첫 실행 시 로딩 있음)"):
                    result_tf = predict_single(user_text, "transformer_v3")
                render_result(result_tf)

            tokens_preview = tokenize_input(user_text).split()[:20]
            st.markdown(f"**사용된 토큰 (앞 20개):** `{' '.join(tokens_preview)}`")
            st.caption(
                "KoNLPy Okt 형태소 분석 사용"
                if _okt_available
                else "공백 기반 간단 분석 모드"
            )
        else:
            with st.spinner(f"{sel_model_label} 분석 중..."):
                result = predict_single(user_text, sel_model)
            st.markdown("#### 분석 결과")
            render_result(result)
            tokens_preview = tokenize_input(user_text).split()[:20]
            st.markdown(f"**사용된 토큰 (앞 20개):** `{' '.join(tokens_preview)}`")
            st.caption(
                "KoNLPy Okt 형태소 분석 사용"
                if _okt_available
                else "공백 기반 간단 분석 모드"
            )
