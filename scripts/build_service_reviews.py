"""
서비스용 리뷰 테이블 생성 스크립트.

입력 파일 (수정 금지):
    preprocessed_v3/train.parquet
    preprocessed_v3/val.parquet
    preprocessed_v3/ambiguous.parquet
    preprocessed_v3/lstm_v3_preds.parquet

생성 파일:
    preprocessed_v3/service_reviews.parquet
    preprocessed_v3/service_reviews_preview.csv
    reports/service_reviews_check.md
    reports/service_reviews_check.json
    reports/service_reviews_manual_review_samples.csv
    reports/service_reviews_manual_review_samples.md

Usage:
    C:\\Users\\user\\anaconda3\\envs\\oliveyoung\\python.exe scripts/build_service_reviews.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from recommendation.normalization import normalize_skin_concern, normalize_skin_type

_DATA_DIR    = _ROOT / "preprocessed_v3"
_REPORTS_DIR = _ROOT / "reports"

TRAIN_PATH           = _DATA_DIR / "train.parquet"
VAL_PATH             = _DATA_DIR / "val.parquet"
PREDS_PATH           = _DATA_DIR / "lstm_v3_preds.parquet"
AMBIGUOUS_PATH       = _DATA_DIR / "ambiguous.parquet"
SERVICE_REVIEWS_PATH = _DATA_DIR / "service_reviews.parquet"
PREVIEW_PATH         = _DATA_DIR / "service_reviews_preview.csv"

PROTECTED_FILES = [TRAIN_PATH, VAL_PATH, AMBIGUOUS_PATH, PREDS_PATH]

SERVICE_COLS = [
    "platform", "product_id", "review_id", "product_name", "brand", "category", "price",
    "rating", "review_text", "clean_review", "review_date", "helpful_count",
    "photo_exists", "raw_url",
    "sentiment_label", "sentiment_id", "label_confidence", "label_source",
    "is_ambiguous", "ambiguous_reason",
    "lstm_v3_pred", "predicted_sentiment",
    "skin_type", "skin_concern",
    "base_skin_type", "skin_type_tags", "skin_need_tags", "skin_type_normalization_status",
    "skin_concern_tags", "skin_concern_codes", "skin_concern_normalization_status",
    "has_base_skin_type", "has_skin_concern_tags", "product_key",
]

REQUIRED_COLS = [
    "platform", "product_id", "review_id", "product_name", "brand", "category", "price",
    "rating", "review_text", "review_date", "skin_type", "skin_concern",
    "helpful_count", "clean_review", "sentiment_label", "sentiment_id",
    "label_confidence", "label_source", "is_ambiguous", "tokens_str",
]

SAMPLE_BASE_COLS = [
    "platform", "product_key", "product_id", "review_id",
    "product_name", "brand", "category", "rating", "review_text",
    "sentiment_label", "lstm_v3_pred", "predicted_sentiment",
    "skin_type", "base_skin_type", "skin_type_tags", "skin_need_tags",
    "skin_type_normalization_status",
    "skin_concern", "skin_concern_tags", "skin_concern_codes",
    "skin_concern_normalization_status",
]

_INT_MAP = {0: "negative", 1: "neutral", 2: "positive"}
_STR_VALID = {"negative", "neutral", "positive"}


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _record_mtimes() -> dict:
    return {str(p): os.path.getmtime(p) if p.exists() else None for p in PROTECTED_FILES}


def _check_mtimes(before: dict, after: dict) -> list[str]:
    return [
        f"MODIFIED: {k} ({before[k]} → {after.get(k)})"
        for k in before
        if before[k] != after.get(k)
    ]


def _arr_nonempty(x) -> bool:
    """list 또는 numpy array가 비어있지 않은지 확인 (parquet reload 대응)."""
    try:
        return len(x) > 0
    except TypeError:
        return False


def _top_counter(series_of_lists: pd.Series, n: int = 20) -> list[tuple]:
    c: Counter = Counter()
    for lst in series_of_lists:
        if _arr_nonempty(lst):
            try:
                c.update(lst)
            except TypeError:
                pass
    return c.most_common(n)


def _df_to_md(df: pd.DataFrame) -> str:
    cols = df.columns.tolist()
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep    = "| " + " | ".join("---" for _ in cols) + " |"
    rows = []
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            val = row[c]
            if isinstance(val, list):
                val = str(val)
            cells.append(str(val).replace("|", "\\|").replace("\n", " "))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + rows)


def _to_sentiment(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip().lower()
    if s in _STR_VALID:
        return s
    try:
        return _INT_MAP.get(int(float(s)))
    except (ValueError, TypeError):
        return None


# ── 처리 단계 ─────────────────────────────────────────────────────────────────

def _load_data() -> tuple[pd.DataFrame, dict]:
    print("[1/9] train + val 로드 중...")
    train = pd.read_parquet(TRAIN_PATH)
    val   = pd.read_parquet(VAL_PATH)
    df    = pd.concat([train, val], ignore_index=True)

    n_train = len(train)
    n_val   = len(val)
    n_total = len(df)
    n_dup   = int(df["review_id"].duplicated().sum())

    missing_cols = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing_cols:
        print(f"  [경고] 필수 컬럼 누락: {missing_cols}")
    else:
        print("  필수 컬럼 모두 존재")

    print(f"  train {n_train:,} + val {n_val:,} = {n_total:,}행  |  review_id 중복: {n_dup}")
    return df, {
        "train_rows": n_train,
        "val_rows": n_val,
        "total_before_merge": n_total,
        "review_id_duplicates_before_merge": n_dup,
        "missing_required_cols": missing_cols,
    }


def _merge_preds(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    print("[2/9] lstm_v3_preds 로드 및 merge 중...")
    preds = pd.read_parquet(PREDS_PATH)
    print(f"  preds 컬럼: {list(preds.columns)}  |  행수: {len(preds):,}")

    pred_cols = [c for c in preds.columns if c != "review_id"]
    if len(pred_cols) != 1:
        raise ValueError(f"예상치 못한 preds 컬럼: {list(preds.columns)}")
    pred_col_original = pred_cols[0]
    print(f"  pred 컬럼: {pred_col_original!r}  |  샘플 값: {preds[pred_col_original].dropna().unique()[:5].tolist()}")

    before = len(df)
    df = df.merge(preds[["review_id", pred_col_original]], on="review_id", how="left")
    after = len(df)

    if pred_col_original != "lstm_v3_pred":
        df = df.rename(columns={pred_col_original: "lstm_v3_pred"})
        print(f"  컬럼명 변경: {pred_col_original} → lstm_v3_pred")

    n_missing = int(df["lstm_v3_pred"].isna().sum())

    df["predicted_sentiment"] = df["lstm_v3_pred"].apply(_to_sentiment)

    unexpected_mask = df["predicted_sentiment"].isna() & df["lstm_v3_pred"].notna()
    n_unexpected = int(unexpected_mask.sum())
    unexpected_vals = (
        df.loc[unexpected_mask, "lstm_v3_pred"].value_counts().head(10).to_dict()
        if n_unexpected else {}
    )

    print(f"  merge: {before:,} → {after:,}행  |  lstm_v3_pred 결측: {n_missing}  |  예외값: {n_unexpected}")

    return df, {
        "rows_before_merge": before,
        "rows_after_merge": after,
        "lstm_v3_pred_missing": n_missing,
        "pred_col_original": pred_col_original,
        "predicted_sentiment_unexpected": n_unexpected,
        "unexpected_values": {str(k): v for k, v in unexpected_vals.items()},
    }


def _apply_normalizations(df: pd.DataFrame) -> pd.DataFrame:
    print("[3/9] 정규화 적용 중...")
    df = df.copy()
    st = df["skin_type"].apply(normalize_skin_type)
    sc = df["skin_concern"].apply(normalize_skin_concern)

    df["base_skin_type"]                    = st.apply(lambda d: d["base_skin_type"])
    df["skin_type_tags"]                    = st.apply(lambda d: d["skin_type_tags"])
    df["skin_need_tags"]                    = st.apply(lambda d: d["skin_need_tags"])
    df["skin_type_normalization_status"]    = st.apply(lambda d: d["skin_type_normalization_status"])
    df["skin_concern_tags"]                 = sc.apply(lambda d: d["skin_concern_tags"])
    df["skin_concern_codes"]               = sc.apply(lambda d: d["skin_concern_codes"])
    df["skin_concern_normalization_status"] = sc.apply(lambda d: d["skin_concern_normalization_status"])
    print("  완료")
    return df


def _create_derived(df: pd.DataFrame) -> pd.DataFrame:
    print("[4/9] 보조 컬럼 생성 중...")
    df["has_base_skin_type"]    = df["base_skin_type"].notna()
    df["has_skin_concern_tags"] = df["skin_concern_tags"].apply(
        lambda x: isinstance(x, list) and len(x) > 0
    )
    df["product_key"] = df["platform"].astype(str) + "::" + df["product_id"].astype(str)
    print("  완료")
    return df


def _save_and_verify(df: pd.DataFrame, mtimes_before: dict) -> tuple[pd.DataFrame, dict]:
    print("[5/9] service_reviews.parquet 저장 및 검증 중...")

    n_dup = int(df["review_id"].duplicated().sum())
    if n_dup > 0:
        print(f"  [경고] review_id 중복 {n_dup}건 → 첫 번째 행 보존")
        df = df.drop_duplicates(subset=["review_id"], keep="first")

    available_cols   = [c for c in SERVICE_COLS if c in df.columns]
    missing_svc_cols = [c for c in SERVICE_COLS if c not in df.columns]
    if missing_svc_cols:
        print(f"  [경고] service_reviews 컬럼 누락: {missing_svc_cols}")

    service_df = df[available_cols].reset_index(drop=True)
    service_df.to_parquet(SERVICE_REVIEWS_PATH, index=False)
    print(f"  저장 완료: {SERVICE_REVIEWS_PATH.name}  ({len(service_df):,}행)")

    print("  재로드 검증 중...")
    df_reload = pd.read_parquet(SERVICE_REVIEWS_PATH)

    n_rows    = len(df_reload)
    n_dup_r   = int(df_reload["review_id"].duplicated().sum())
    n_pk_null = int(df_reload["product_key"].isna().sum())
    n_ps_null = int(df_reload["predicted_sentiment"].isna().sum())
    ps_vals   = sorted(df_reload["predicted_sentiment"].dropna().unique().tolist())

    bst_status = df_reload["skin_type_normalization_status"].value_counts().to_dict()
    n_ok     = int(bst_status.get("ok", 0))
    n_nobase = int(bst_status.get("no_base_skin_type", 0))
    n_miss   = int(bst_status.get("missing", 0))

    mtimes_after = {str(p): os.path.getmtime(p) if p.exists() else None for p in PROTECTED_FILES}
    mtime_changes = _check_mtimes(mtimes_before, mtimes_after)

    verify = {
        "reload_rows": n_rows,
        "review_id_dup_after_reload": n_dup_r,
        "product_key_null": n_pk_null,
        "predicted_sentiment_null": n_ps_null,
        "predicted_sentiment_unique": ps_vals,
        "ps_only_3_values": set(ps_vals) <= _STR_VALID,
        "bst_ok_count": n_ok,
        "bst_nobase_count": n_nobase,
        "bst_missing_count": n_miss,
        "protected_mtime_changes": mtime_changes,
        "mtimes_after": mtimes_after,
    }

    print(f"  재로드 {n_rows:,}행 | review_id 중복 {n_dup_r} | product_key 결측 {n_pk_null}")
    print(f"  predicted_sentiment 결측 {n_ps_null} | 고유값 {ps_vals}")
    print(f"  bst: ok={n_ok:,} / no_base={n_nobase:,} / missing={n_miss:,}")
    print(f"  no_base_skin_type 831건 일치: {'✓' if n_nobase == 831 else f'✗ 실제:{n_nobase}'}")
    if mtime_changes:
        for msg in mtime_changes:
            print(f"  [오류] {msg}")
    else:
        print("  보호 파일 mtime 변경 없음 ✓")

    return df_reload, verify


def _build_preview(df: pd.DataFrame) -> None:
    print("[6/9] preview CSV 생성 중...")
    n_each = 30

    def _s(mask):
        sub = df[mask]
        return sub.head(n_each) if len(sub) >= n_each else sub

    parts = [
        _s(df["base_skin_type"].notna()),
        _s(df["skin_type_normalization_status"] == "missing"),
        _s(df["skin_type_normalization_status"] == "no_base_skin_type"),
        _s(df["predicted_sentiment"] == "negative"),
        _s(df["predicted_sentiment"] == "neutral"),
        _s(df["predicted_sentiment"] == "positive"),
        _s(df["skin_concern_codes"].apply(_arr_nonempty)),
    ]
    for plat in df["platform"].dropna().unique():
        parts.append(_s(df["platform"] == plat))

    preview = (
        pd.concat(parts, ignore_index=True)
        .drop_duplicates(subset=["review_id"])
        .head(200)
    )
    for col in preview.columns:
        if preview[col].apply(lambda x: isinstance(x, list)).any():
            preview[col] = preview[col].apply(lambda x: str(x) if isinstance(x, list) else x)

    preview.to_csv(PREVIEW_PATH, index=False, encoding="utf-8-sig")
    print(f"  저장 완료: {PREVIEW_PATH.name}  ({len(preview)}행)")


def _collect_samples(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    print("[7/9] 수동 검수 샘플 수집 중...")
    avail = [c for c in SAMPLE_BASE_COLS if c in df.columns]

    def _pick(mask=None, n: int = 20, seed: int | None = None) -> pd.DataFrame:
        sub = df[mask].copy() if mask is not None else df.copy()
        if seed is not None:
            sub = sub.sample(min(n, len(sub)), random_state=seed)
        else:
            sub = sub.head(n)
        return sub[avail].reset_index(drop=True)

    mismatch_mask = (
        df["sentiment_label"].notna()
        & df["predicted_sentiment"].notna()
        & (df["sentiment_label"] != df["predicted_sentiment"])
    )

    samples: dict[str, pd.DataFrame] = {
        "merge_check_samples":       _pick(n=20, seed=42),
        "negative_review_samples":   _pick(df["predicted_sentiment"] == "negative"),
        "positive_review_samples":   _pick(df["predicted_sentiment"] == "positive"),
        "neutral_review_samples":    _pick(df["predicted_sentiment"] == "neutral"),
        "base_skin_type_samples":    _pick(df["base_skin_type"].notna()),
        "no_base_skin_type_samples": _pick(df["skin_type_normalization_status"] == "no_base_skin_type"),
        "missing_skin_type_samples": _pick(df["skin_type_normalization_status"] == "missing"),
        "skin_concern_code_samples": _pick(df["skin_concern_codes"].apply(_arr_nonempty)),
        "mismatch_samples": _pick(mismatch_mask),
    }

    plat_parts = []
    for plat in ["musinsa", "oliveyoung", "coupang"]:
        sub = _pick(df["platform"] == plat, n=7)
        plat_parts.append(sub)
    samples["platform_samples"] = pd.concat(plat_parts, ignore_index=True)

    for name, sdf in samples.items():
        print(f"  {name}: {len(sdf)}개")
    return samples


# ── 리포트 ────────────────────────────────────────────────────────────────────

def _build_report_data(df: pd.DataFrame, load_info: dict, merge_info: dict, verify: dict) -> dict:
    total = len(df)

    ps_dist  = {str(k): int(v) for k, v in df["predicted_sentiment"].value_counts(dropna=False).items()}
    sl_dist  = {str(k): int(v) for k, v in df["sentiment_label"].value_counts(dropna=False).items()}
    n_mis    = int(
        (df["sentiment_label"].notna() & df["predicted_sentiment"].notna()
         & (df["sentiment_label"] != df["predicted_sentiment"])).sum()
    )

    bst_dist   = {str(k): int(v) for k, v in df["base_skin_type"].value_counts(dropna=False).head(10).items()}
    st_status  = {str(k): int(v) for k, v in df["skin_type_normalization_status"].value_counts().items()}
    has_bst    = int(df["has_base_skin_type"].sum())

    sc_status  = {str(k): int(v) for k, v in df["skin_concern_normalization_status"].value_counts().items()}
    has_sct    = int(df["has_skin_concern_tags"].sum())
    top_codes  = _top_counter(df["skin_concern_codes"], 20)
    top_tags   = _top_counter(df["skin_concern_tags"], 20)

    plat_counts = {str(k): int(v) for k, v in df["platform"].value_counts().items()}
    cat_counts  = {str(k): int(v) for k, v in df["category"].value_counts().head(20).items()}
    n_pk        = int(df["product_key"].nunique())

    pk_series = df.groupby("product_key").size()
    pk_stats  = {
        "min": int(pk_series.min()),
        "max": int(pk_series.max()),
        "mean": round(float(pk_series.mean()), 1),
        "median": float(pk_series.median()),
        "top10": {str(k): int(v) for k, v in pk_series.nlargest(10).items()},
    }

    plat_bst: dict = {}
    for plat in df["platform"].dropna().unique():
        sub = df[df["platform"] == plat]
        n_has = int(sub["has_base_skin_type"].sum())
        plat_bst[str(plat)] = {"has_base": n_has, "total": len(sub), "pct": round(n_has / len(sub) * 100, 1)}

    plat_sc: dict = {}
    for plat in df["platform"].dropna().unique():
        sub = df[df["platform"] == plat]
        n_has = int(sub["has_skin_concern_tags"].sum())
        plat_sc[str(plat)] = {"has_tags": n_has, "total": len(sub), "pct": round(n_has / len(sub) * 100, 1)}

    bst_ps: dict = {}
    for bst in df["base_skin_type"].dropna().unique():
        sub = df[df["base_skin_type"] == bst]
        bst_ps[str(bst)] = {str(k): int(v) for k, v in sub["predicted_sentiment"].value_counts().items()}

    bst_neg  = {str(k): int(v) for k, v in
                df[df["predicted_sentiment"] == "negative"].groupby("base_skin_type").size().items()}
    plat_neg = {str(k): int(v) for k, v in
                df[df["predicted_sentiment"] == "negative"]["platform"].value_counts().items()}

    return {
        "total_rows": total,
        "load_info": load_info,
        "merge_info": merge_info,
        "verify": verify,
        "sentiment": {
            "predicted_sentiment_dist": ps_dist,
            "sentiment_label_dist": sl_dist,
            "mismatch_count": n_mis,
            "mismatch_pct": round(n_mis / total * 100, 2),
        },
        "skin_type": {
            "base_skin_type_dist": bst_dist,
            "status_dist": st_status,
            "has_base_skin_type_count": has_bst,
            "has_base_skin_type_pct": round(has_bst / total * 100, 1),
            "no_base_skin_type_count": int(st_status.get("no_base_skin_type", 0)),
            "missing_count": int(st_status.get("missing", 0)),
            "platform_bst_coverage": plat_bst,
        },
        "skin_concern": {
            "status_dist": sc_status,
            "has_tags_count": has_sct,
            "has_tags_pct": round(has_sct / total * 100, 1),
            "top_codes": top_codes,
            "top_tags": top_tags,
            "platform_sc_coverage": plat_sc,
        },
        "service": {
            "platform_counts": plat_counts,
            "category_counts": cat_counts,
            "product_key_count": n_pk,
            "product_key_review_stats": pk_stats,
            "bst_predicted_sentiment_dist": bst_ps,
            "bst_negative_counts": bst_neg,
            "platform_negative_counts": plat_neg,
        },
    }


def _write_json(report: dict) -> None:
    def _conv(obj):
        if isinstance(obj, dict):
            return {str(k): _conv(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_conv(i) for i in obj]
        return obj

    path = _REPORTS_DIR / "service_reviews_check.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_conv(report), f, ensure_ascii=False, indent=2, default=str)
    print(f"  저장: {path.name}")


def _write_md(report: dict) -> None:
    li = report["load_info"]
    mi = report["merge_info"]
    vi = report["verify"]
    se = report["sentiment"]
    sk = report["skin_type"]
    sc = report["skin_concern"]
    sv = report["service"]

    _nobase_ok = "✓" if vi["bst_nobase_count"] == 831 else f"✗ (실제 {vi['bst_nobase_count']}건)"
    _ps3ok     = "✓" if vi["ps_only_3_values"] else "✗"
    _prot_ok   = "**보호 파일 mtime 변경 없음 ✓**"

    lines = [
        "# Service Reviews Check Report",
        "",
        "생성일: 2026-06-27",
        "",
        "## 1. 기본 수치",
        "",
        "| 항목 | 값 |",
        "| --- | --- |",
        f"| train row 수 | {li['train_rows']:,} |",
        f"| val row 수 | {li['val_rows']:,} |",
        f"| merge 전 전체 row 수 | {li['total_before_merge']:,} |",
        f"| merge 후 전체 row 수 | {mi['rows_after_merge']:,} |",
        f"| review_id 중복 수 | {li['review_id_duplicates_before_merge']} |",
        f"| lstm_v3_pred 결측 수 | {mi['lstm_v3_pred_missing']} |",
        f"| predicted_sentiment 예외값 수 | {mi['predicted_sentiment_unexpected']} |",
        f"| service_reviews.parquet row 수 (재로드) | {vi['reload_rows']:,} |",
        f"| product_key 결측 수 | {vi['product_key_null']} |",
        f"| predicted_sentiment 결측 수 (재로드 후) | {vi['predicted_sentiment_null']} |",
        "",
        "## 2. 저장 후 검증 결과",
        "",
        f"- 재로드 row 수: {vi['reload_rows']:,}",
        f"- review_id 중복: {vi['review_id_dup_after_reload']}",
        f"- predicted_sentiment 고유값: {vi['predicted_sentiment_unique']}",
        f"- predicted_sentiment 3종 한정: {_ps3ok}",
        f"- base_skin_type ok: {vi['bst_ok_count']:,} / no_base: {vi['bst_nobase_count']:,} / missing: {vi['bst_missing_count']:,}",
        f"- no_base_skin_type 831건 일치: {_nobase_ok}",
        "",
    ]

    if vi["protected_mtime_changes"]:
        lines += ["**⚠️ 보호 파일 변경 감지**", ""]
        for msg in vi["protected_mtime_changes"]:
            lines.append(f"- {msg}")
        lines.append("")
    else:
        lines += [_prot_ok, ""]

    lines += [
        "## 3. 감성 예측 결합 결과",
        "",
        "### predicted_sentiment 분포",
        "",
        "| 값 | 수 |",
        "| --- | --- |",
    ]
    for k, v in se["predicted_sentiment_dist"].items():
        lines.append(f"| {k} | {v:,} |")

    lines += [
        "",
        "### sentiment_label 분포",
        "",
        "| 값 | 수 |",
        "| --- | --- |",
    ]
    for k, v in se["sentiment_label_dist"].items():
        lines.append(f"| {k} | {v:,} |")

    lines += [
        "",
        f"### 불일치 수: {se['mismatch_count']:,}건 ({se['mismatch_pct']}%)",
        "",
        "## 4. 피부 타입 정규화 결과",
        "",
        "### base_skin_type 분포",
        "",
        "| base_skin_type | 수 |",
        "| --- | --- |",
    ]
    for k, v in sk["base_skin_type_dist"].items():
        lines.append(f"| {k} | {v:,} |")

    lines += [
        "",
        "### skin_type_normalization_status 분포",
        "",
        "| status | 수 |",
        "| --- | --- |",
    ]
    for k, v in sk["status_dist"].items():
        lines.append(f"| {k} | {v:,} |")

    lines += [
        "",
        f"- has_base_skin_type: {sk['has_base_skin_type_count']:,}건 ({sk['has_base_skin_type_pct']}%)",
        f"- no_base_skin_type: {sk['no_base_skin_type_count']:,}건",
        f"- missing: {sk['missing_count']:,}건",
        "",
        "### 플랫폼별 base_skin_type 커버리지",
        "",
        "| 플랫폼 | has_base | 전체 | 비율 |",
        "| --- | --- | --- | --- |",
    ]
    for plat, d in sk["platform_bst_coverage"].items():
        lines.append(f"| {plat} | {d['has_base']:,} | {d['total']:,} | {d['pct']}% |")

    lines += [
        "",
        "## 5. 피부 고민 정규화 결과",
        "",
        "### skin_concern_normalization_status 분포",
        "",
        "| status | 수 |",
        "| --- | --- |",
    ]
    for k, v in sc["status_dist"].items():
        lines.append(f"| {k} | {v:,} |")

    lines += [
        "",
        f"- has_skin_concern_tags: {sc['has_tags_count']:,}건 ({sc['has_tags_pct']}%)",
        "",
        "### 플랫폼별 skin_concern_tags 커버리지",
        "",
        "| 플랫폼 | has_tags | 전체 | 비율 |",
        "| --- | --- | --- | --- |",
    ]
    for plat, d in sc["platform_sc_coverage"].items():
        lines.append(f"| {plat} | {d['has_tags']:,} | {d['total']:,} | {d['pct']}% |")

    lines += [
        "",
        "### skin_concern_codes 상위 20",
        "",
        "| 코드 | 수 |",
        "| --- | --- |",
    ]
    for code, cnt in sc["top_codes"]:
        lines.append(f"| {code} | {cnt:,} |")

    lines += [
        "",
        "## 6. 서비스 관점 수치",
        "",
        "### 플랫폼별 리뷰 수",
        "",
        "| 플랫폼 | 수 |",
        "| --- | --- |",
    ]
    for k, v in sv["platform_counts"].items():
        lines.append(f"| {k} | {v:,} |")

    lines += [
        "",
        "### 카테고리별 리뷰 수 (상위 20)",
        "",
        "| 카테고리 | 수 |",
        "| --- | --- |",
    ]
    for k, v in sv["category_counts"].items():
        lines.append(f"| {k} | {v:,} |")

    lines += [
        "",
        f"### product_key 수: {sv['product_key_count']:,}",
        "",
        "### product_key별 리뷰 수 분포",
        "",
        f"- min: {sv['product_key_review_stats']['min']}",
        f"- max: {sv['product_key_review_stats']['max']}",
        f"- mean: {sv['product_key_review_stats']['mean']}",
        f"- median: {sv['product_key_review_stats']['median']}",
        "",
        "### base_skin_type별 predicted_sentiment 분포",
        "",
        "| base_skin_type | negative | neutral | positive |",
        "| --- | --- | --- | --- |",
    ]
    for bst, dist in sv["bst_predicted_sentiment_dist"].items():
        neg = dist.get("negative", 0)
        neu = dist.get("neutral", 0)
        pos = dist.get("positive", 0)
        lines.append(f"| {bst} | {neg:,} | {neu:,} | {pos:,} |")

    lines += [
        "",
        "### base_skin_type별 negative 리뷰 수",
        "",
        "| base_skin_type | negative 수 |",
        "| --- | --- |",
    ]
    for k, v in sv["bst_negative_counts"].items():
        lines.append(f"| {k} | {v:,} |")

    lines += [
        "",
        "### 플랫폼별 negative 리뷰 수",
        "",
        "| 플랫폼 | negative 수 |",
        "| --- | --- |",
    ]
    for k, v in sv["platform_negative_counts"].items():
        lines.append(f"| {k} | {v:,} |")

    lines += [
        "",
        "## 7. 품질 판단",
        "",
        "### Step 3 product_skin_aggregates 생성 가능 여부",
        "",
        "- 가능: has_base_skin_type=True이고 predicted_sentiment가 있는 row 사용",
        "- 제외 조건: base_skin_type is None (no_base_skin_type 831건 + missing 전체)",
        "",
        "### 피부 타입 집계에서 제외해야 할 row 조건",
        "",
        "- `has_base_skin_type == False` 모두 제외",
        "- coupang 플랫폼: skin_type 없으므로 전체 has_base_skin_type=False",
        "",
        "### 추천 점수 산정 시 주의할 점",
        "",
        "- predicted_sentiment는 BiLSTM 예측 (macro_f1 0.666, neutral_recall 0.586 — neutral 성능 낮음)",
        "- sentiment_label(약한 라벨)과의 불일치 비율을 UI에서 참고할 것",
        "- 부정 리뷰 탐색 서비스이므로 negative recall이 핵심 지표",
        "",
        "### 부정 리뷰 탐색 UI에서 사용할 수 있는 컬럼",
        "",
        "- 필터: `base_skin_type`, `predicted_sentiment == 'negative'`, `product_key`, `platform`",
        "- 표시: `review_text`, `rating`, `review_date`, `brand`, `product_name`, `category`",
        "- 보조 표시: `skin_type_tags`, `skin_need_tags`, `skin_concern_tags`",
        "",
        "### 아직 위험한 부분",
        "",
        "- C09/C10/C11/C12/C13 코드 의미 미확인 → skin_concern_codes는 UI 직접 노출 금지",
        "- neutral 예측 recall 0.586 → neutral 리뷰의 오분류 가능",
        "- coupang 전체 base_skin_type 없음 → 피부 타입별 집계 불가",
        "",
        "## 수동 샘플 검수 결과",
        "",
        "- 직접 확인한 샘플 수: (스크립트 실행 후 직접 확인 예정)",
        "- 확인한 파일: reports/service_reviews_manual_review_samples.csv",
        "- 샘플링 그룹: merge_check_samples, negative_review_samples, positive_review_samples,",
        "  neutral_review_samples, base_skin_type_samples, no_base_skin_type_samples,",
        "  missing_skin_type_samples, skin_concern_code_samples, platform_samples, mismatch_samples",
        "- 정상으로 판단한 예시: (직접 확인 후 기록)",
        "- 이상하거나 애매한 예시: (직접 확인 후 기록)",
        "- 수정한 규칙: (직접 확인 후 기록)",
        "- 아직 남은 위험: C09/C10/C11/C12/C13 코드 의미 미확인",
        "- Step 3 진행 가능 여부: (직접 확인 후 판단)",
        "",
        "### negative 샘플 판단",
        "",
        "- 실제 부정처럼 보이는 샘플이 대부분인지: (직접 확인 후 기록)",
        "- 애매한 샘플 예시: (직접 확인 후 기록)",
        "- 주의할 점: (직접 확인 후 기록)",
        "",
        "### mismatch 샘플 판단",
        "",
        "- 별점/약한 라벨과 모델 예측이 달라진 이유로 보이는 것: (직접 확인 후 기록)",
        "- 서비스에서 predicted_sentiment를 우선 써도 되는지: (직접 확인 후 판단)",
    ]

    path = _REPORTS_DIR / "service_reviews_check.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  저장: {path.name}")


def _write_samples(samples: dict) -> None:
    parts = []
    for group, sdf in samples.items():
        if sdf.empty:
            continue
        tmp = sdf.copy()
        tmp.insert(0, "sample_group", group)
        for col in tmp.columns:
            if tmp[col].apply(lambda x: isinstance(x, list)).any():
                tmp[col] = tmp[col].apply(lambda x: str(x) if isinstance(x, list) else x)
        parts.append(tmp)

    if parts:
        combined = pd.concat(parts, ignore_index=True)
        csv_path = _REPORTS_DIR / "service_reviews_manual_review_samples.csv"
        combined.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"  저장: {csv_path.name}")

    md_lines = ["# 수동 검수 샘플 (Service Reviews)", ""]
    for group, sdf in samples.items():
        md_lines.append(f"\n## {group} ({len(sdf)}개)\n")
        if sdf.empty:
            md_lines.append("_(해당 샘플 없음)_")
            continue
        display = sdf.copy()
        for col in display.columns:
            if display[col].apply(lambda x: isinstance(x, list)).any():
                display[col] = display[col].apply(lambda x: str(x) if isinstance(x, list) else x)
        if "review_text" in display.columns:
            display["review_text"] = display["review_text"].apply(
                lambda x: str(x)[:80] + "..." if isinstance(x, str) and len(x) > 80 else x
            )
        md_lines.append(_df_to_md(display))

    md_path = _REPORTS_DIR / "service_reviews_manual_review_samples.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"  저장: {md_path.name}")


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    print("=== Step 2: service_reviews.parquet 생성 ===\n")

    print("[0/9] 보호 파일 mtime 기록...")
    mtimes_before = _record_mtimes()
    for path, mtime in mtimes_before.items():
        print(f"  {Path(path).name}: {mtime}")

    df, load_info          = _load_data()
    df, merge_info         = _merge_preds(df)
    df                     = _apply_normalizations(df)
    df                     = _create_derived(df)
    df_service, verify     = _save_and_verify(df, mtimes_before)

    _build_preview(df_service)
    samples = _collect_samples(df_service)

    print("[8/9] 리포트 생성 중...")
    report = _build_report_data(df_service, load_info, merge_info, verify)
    _write_json(report)
    _write_md(report)

    print("[9/9] 수동 검수 샘플 저장 중...")
    _write_samples(samples)

    # 최종 mtime 재확인
    mtimes_final  = {str(p): os.path.getmtime(p) if p.exists() else None for p in PROTECTED_FILES}
    final_changes = _check_mtimes(mtimes_before, mtimes_final)

    print("\n=== 핵심 수치 요약 ===")
    li, mi, vi = load_info, merge_info, verify
    se, sk, sc2, sv = report["sentiment"], report["skin_type"], report["skin_concern"], report["service"]
    print(f"  train {li['train_rows']:,} + val {li['val_rows']:,} = {li['total_before_merge']:,}행")
    print(f"  merge 후: {mi['rows_after_merge']:,}행  |  lstm_v3_pred 결측: {mi['lstm_v3_pred_missing']}")
    print(f"  service_reviews: {vi['reload_rows']:,}행  |  product_key {sv['product_key_count']:,}개")
    print(f"  predicted_sentiment: {se['predicted_sentiment_dist']}")
    print(f"  sentiment_label:     {se['sentiment_label_dist']}")
    print(f"  불일치: {se['mismatch_count']:,}건 ({se['mismatch_pct']}%)")
    print(f"  base_skin_type ok: {sk['has_base_skin_type_count']:,}  "
          f"no_base: {sk['no_base_skin_type_count']:,}  missing: {sk['missing_count']:,}")
    print(f"  has_skin_concern_tags: {sc2['has_tags_count']:,}건")
    if final_changes:
        print("\n⚠️  보호 파일 변경 감지!")
        for msg in final_changes:
            print(f"  {msg}")
    else:
        print("\n  보호 파일 mtime 변경 없음 ✓")
    print("\n완료!")


if __name__ == "__main__":
    main()
