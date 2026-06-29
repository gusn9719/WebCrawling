"""
Step 3: product_skin_aggregates 생성 스크립트.

service_reviews.parquet (402,438 rows)를 기반으로 상품별/피부타입별 집계 테이블을 생성.

생성 파일:
  preprocessed_v3/product_skin_aggregates.parquet
  preprocessed_v3/product_skin_aggregates_preview.csv
  reports/product_skin_aggregates_check.md
  reports/product_skin_aggregates_check.json
  reports/product_skin_aggregates_manual_review_samples.csv
  reports/product_skin_aggregates_manual_review_samples.md
"""
from __future__ import annotations

import json
import sys
import time
import textwrap
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# [3] aggregation.py 존재 확인
_AGG_PATH = ROOT / "recommendation" / "aggregation.py"
if not _AGG_PATH.exists():
    print(f"[ERROR] recommendation/aggregation.py not found at {_AGG_PATH}")
    print("  → 파일을 먼저 생성하거나 경로를 확인하세요.")
    sys.exit(1)

from recommendation.aggregation import (
    arr_to_list,
    collect_top_tags,
    get_caution_level,
    get_caution_message,
    get_confidence_label,
    safe_rate,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
PREPROCESSED = ROOT / "preprocessed_v3"
REPORTS = ROOT / "reports"
DOCS_WORKLOG = ROOT / "docs" / "worklog"

SERVICE_REVIEWS = PREPROCESSED / "service_reviews.parquet"
OUTPUT_PARQUET = PREPROCESSED / "product_skin_aggregates.parquet"
OUTPUT_PREVIEW = PREPROCESSED / "product_skin_aggregates_preview.csv"
REPORT_MD = REPORTS / "product_skin_aggregates_check.md"
REPORT_JSON = REPORTS / "product_skin_aggregates_check.json"
MANUAL_CSV = REPORTS / "product_skin_aggregates_manual_review_samples.csv"
MANUAL_MD = REPORTS / "product_skin_aggregates_manual_review_samples.md"
WORKLOG = DOCS_WORKLOG / "2026-06-27.md"

# ── Constants ─────────────────────────────────────────────────────────────────
EXPECTED_ROWS = 402_438
EXPECTED_NO_BASE = 831
VALID_SENTIMENTS = {"negative", "neutral", "positive"}
SKIN_TYPES = ["지성", "건성", "민감성", "복합성", "중성"]

FINAL_COLS = [
    "product_key", "platform", "product_id", "product_name", "brand",
    "category", "price", "base_skin_type",
    "total_review_count", "avg_rating",
    "overall_positive_count", "overall_neutral_count", "overall_negative_count",
    "overall_positive_rate", "overall_neutral_rate", "overall_negative_rate",
    "skin_review_count", "skin_positive_count", "skin_neutral_count", "skin_negative_count",
    "skin_positive_rate", "skin_neutral_rate", "skin_negative_rate",
    "skin_confidence_label",
    "top_skin_need_tags", "top_skin_concern_tags", "skin_concern_code_count",
    "has_enough_skin_reviews", "caution_level", "caution_message",
]

MANUAL_COLS = [
    "sample_group", "product_key", "platform", "product_id", "product_name",
    "brand", "category", "base_skin_type",
    "total_review_count", "skin_review_count",
    "skin_positive_count", "skin_neutral_count", "skin_negative_count",
    "skin_positive_rate", "skin_neutral_rate", "skin_negative_rate",
    "skin_confidence_label", "caution_level", "caution_message",
    "top_skin_need_tags", "top_skin_concern_tags", "skin_concern_code_count",
    "manual_check_note",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tags_to_str(val) -> str:
    lst = arr_to_list(val)
    return ", ".join(str(t) for t in lst) if lst else ""


def _critical(msg: str) -> None:
    print(f"\n[CRITICAL ERROR] {msg}")
    print("  → 결과 파일을 신뢰할 수 없으므로 중단합니다.")
    sys.exit(1)


# ── Section 1: Load & Validate ────────────────────────────────────────────────

def load_and_validate() -> tuple[pd.DataFrame, dict]:
    print("\n[1] service_reviews.parquet 로드 및 검증")
    df = pd.read_parquet(SERVICE_REVIEWS)

    row_count = len(df)
    print(f"  row 수: {row_count:,}")
    if row_count != EXPECTED_ROWS:
        _critical(f"row 수 불일치: 예상 {EXPECTED_ROWS:,}, 실제 {row_count:,}")

    dup_review = int(df["review_id"].duplicated().sum())
    null_product_key = int(df["product_key"].isna().sum())
    null_sentiment = int(df["predicted_sentiment"].isna().sum())
    unique_sentiments = set(df["predicted_sentiment"].dropna().unique())

    print(f"  review_id 중복: {dup_review}")
    print(f"  product_key null: {null_product_key}")
    print(f"  predicted_sentiment null: {null_sentiment}")
    print(f"  predicted_sentiment 종류: {unique_sentiments}")

    if unique_sentiments != VALID_SENTIMENTS:
        _critical(f"predicted_sentiment 예상치 않은 값: {unique_sentiments}")

    skin_dist = df["base_skin_type"].value_counts(dropna=False)
    print(f"  base_skin_type 분포:\n{skin_dist.to_string()}")

    has_base = int(df["has_base_skin_type"].sum())
    no_base = int((df["skin_type_normalization_status"] == "no_base_skin_type").sum())
    print(f"  has_base_skin_type: {has_base:,}")
    print(f"  no_base_skin_type: {no_base} (예상 {EXPECTED_NO_BASE})")

    if no_base != EXPECTED_NO_BASE:
        print(f"  [WARNING] no_base_skin_type 예상 {EXPECTED_NO_BASE}, 실제 {no_base}")

    stats = {
        "row_count": row_count,
        "dup_review_id": dup_review,
        "null_product_key": null_product_key,
        "null_predicted_sentiment": null_sentiment,
        "has_base_skin_type": has_base,
        "no_base_skin_type": no_base,
        "product_key_count": int(df["product_key"].nunique()),
        "skin_type_dist": {
            str(k): int(v) for k, v in skin_dist.items()
        },
    }
    print("  [OK] 검증 통과")
    return df, stats


# ── Section 2: Overall Product Aggregates ────────────────────────────────────

def build_overall_aggregates(df: pd.DataFrame) -> pd.DataFrame:
    print("\n[2] 전체 상품 집계 생성 (coupang 포함)")
    grp = df.groupby("product_key", sort=False)

    meta = grp.agg(
        platform=("platform", "first"),
        product_id=("product_id", "first"),
        product_name=("product_name", "first"),
        brand=("brand", "first"),
        category=("category", "first"),
        price=("price", "first"),
        total_review_count=("review_id", "count"),
        avg_rating=("rating", "mean"),
    ).reset_index()

    # sentiment counts via unstack
    sent = (
        df.groupby("product_key")["predicted_sentiment"]
        .value_counts()
        .unstack(fill_value=0)
        .reset_index()
    )
    sent.columns.name = None
    for s in ["negative", "neutral", "positive"]:
        if s not in sent.columns:
            sent[s] = 0
    sent = sent.rename(columns={
        "negative": "overall_negative_count",
        "neutral": "overall_neutral_count",
        "positive": "overall_positive_count",
    })[["product_key", "overall_positive_count", "overall_neutral_count", "overall_negative_count"]]

    overall = meta.merge(sent, on="product_key", how="left")

    overall["overall_positive_rate"] = overall.apply(
        lambda r: safe_rate(r["overall_positive_count"], r["total_review_count"]), axis=1
    )
    overall["overall_neutral_rate"] = overall.apply(
        lambda r: safe_rate(r["overall_neutral_count"], r["total_review_count"]), axis=1
    )
    overall["overall_negative_rate"] = overall.apply(
        lambda r: safe_rate(r["overall_negative_count"], r["total_review_count"]), axis=1
    )

    print(f"  전체 상품 수: {len(overall):,}")
    return overall


# ── Section 3: Skin Type Aggregates ──────────────────────────────────────────

def _agg_skin_group(group: pd.DataFrame) -> pd.Series:
    n = len(group)
    pos = int((group["predicted_sentiment"] == "positive").sum())
    neu = int((group["predicted_sentiment"] == "neutral").sum())
    neg = int((group["predicted_sentiment"] == "negative").sum())
    code_count = int(sum(len(arr_to_list(x)) for x in group["skin_concern_codes"]))

    return pd.Series({
        "skin_review_count": n,
        "skin_positive_count": pos,
        "skin_neutral_count": neu,
        "skin_negative_count": neg,
        "skin_positive_rate": safe_rate(pos, n),
        "skin_neutral_rate": safe_rate(neu, n),
        "skin_negative_rate": safe_rate(neg, n),
        "skin_confidence_label": get_confidence_label(n),
        "top_skin_need_tags": collect_top_tags(group["skin_need_tags"], 5),
        "top_skin_concern_tags": collect_top_tags(group["skin_concern_tags"], 5),
        "skin_concern_code_count": code_count,
    })


def build_skin_aggregates(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    print("\n[3] 피부 타입별 집계 생성")

    # 제외 수 분류
    excl_missing = int((df["skin_type_normalization_status"] == "missing").sum())
    excl_no_base = int((df["skin_type_normalization_status"] == "no_base_skin_type").sum())
    excl_null_sent = int(df["predicted_sentiment"].isna().sum())

    skin_df = df[
        (df["has_base_skin_type"] == True) &
        (df["base_skin_type"].notna()) &
        (df["predicted_sentiment"].notna())
    ].copy()

    used = len(skin_df)
    excluded = len(df) - used
    print(f"  사용 row: {used:,}")
    print(f"  제외 row: {excluded:,}")
    print(f"    - base_skin_type missing: {excl_missing:,}")
    print(f"    - no_base_skin_type: {excl_no_base}")
    print(f"    - predicted_sentiment null: {excl_null_sent}")

    print("  groupby 집계 중... (시간 소요)")
    t0 = time.time()
    try:
        skin_agg = (
            skin_df.groupby(["product_key", "base_skin_type"], sort=False)
            .apply(_agg_skin_group, include_groups=False)
            .reset_index()
        )
    except TypeError:
        # pandas < 2.2
        skin_agg = (
            skin_df.groupby(["product_key", "base_skin_type"], sort=False)
            .apply(_agg_skin_group)
            .reset_index()
        )
    elapsed = time.time() - t0
    print(f"  집계 완료: {len(skin_agg):,} rows ({elapsed:.1f}s)")

    skin_agg["caution_level"] = skin_agg.apply(
        lambda r: get_caution_level(int(r["skin_review_count"]), float(r["skin_negative_rate"])),
        axis=1,
    )
    skin_agg["caution_message"] = skin_agg["caution_level"].apply(get_caution_message)
    skin_agg["has_enough_skin_reviews"] = skin_agg["skin_review_count"] >= 5

    stats = {
        "skin_reviews_used": used,
        "skin_reviews_excluded": excluded,
        "excl_base_skin_type_missing": excl_missing,
        "excl_no_base_skin_type": excl_no_base,
        "excl_null_sentiment": excl_null_sent,
        "skin_aggregate_rows": len(skin_agg),
    }
    return skin_agg, stats


# ── Section 4: Join & Finalize ────────────────────────────────────────────────

def build_final(skin_agg: pd.DataFrame, overall: pd.DataFrame) -> pd.DataFrame:
    print("\n[4] 최종 테이블 조인")
    result = skin_agg.merge(overall, on="product_key", how="left")
    result = result[FINAL_COLS]
    print(f"  최종 row 수: {len(result):,}")
    return result


# ── Section 5: Validate ───────────────────────────────────────────────────────

def validate_result(result: pd.DataFrame) -> dict:
    print("\n[5] 검증")

    # --- critical checks ---
    dup_key = int(result.duplicated(["product_key", "base_skin_type"]).sum())
    if dup_key > 0:
        _critical(f"(product_key, base_skin_type) 중복 {dup_key}건 발견")

    null_base = int(result["base_skin_type"].isna().sum())
    if null_base > 0:
        _critical(f"base_skin_type null {null_base}건 발견")

    zero_skin = int((result["skin_review_count"] <= 0).sum())
    if zero_skin > 0:
        _critical(f"skin_review_count <= 0인 row {zero_skin}건 발견")

    skin_sum_mismatch = int((
        result["skin_positive_count"] +
        result["skin_neutral_count"] +
        result["skin_negative_count"] !=
        result["skin_review_count"]
    ).sum())
    if skin_sum_mismatch > 0:
        _critical(f"skin count 합계 불일치 {skin_sum_mismatch}건")

    overall_sum_mismatch = int((
        result["overall_positive_count"] +
        result["overall_neutral_count"] +
        result["overall_negative_count"] !=
        result["total_review_count"]
    ).sum())
    if overall_sum_mismatch > 0:
        _critical(f"overall count 합계 불일치 {overall_sum_mismatch}건")

    print("  [OK] critical 검증 모두 통과")

    # --- warning checks (rate sum deviation) ---
    skin_rate_dev = float((
        result["skin_positive_rate"] +
        result["skin_neutral_rate"] +
        result["skin_negative_rate"] - 1.0
    ).abs().max())
    overall_rate_dev = float((
        result["overall_positive_rate"] +
        result["overall_neutral_rate"] +
        result["overall_negative_rate"] - 1.0
    ).abs().max())

    if skin_rate_dev > 0.001:
        print(f"  [WARNING] skin rate 합계 최대 편차 {skin_rate_dev:.6f} > 0.001")
    else:
        print(f"  skin rate 합계 최대 편차: {skin_rate_dev:.2e} (OK)")
    if overall_rate_dev > 0.001:
        print(f"  [WARNING] overall rate 합계 최대 편차 {overall_rate_dev:.6f} > 0.001")
    else:
        print(f"  overall rate 합계 최대 편차: {overall_rate_dev:.2e} (OK)")

    return {
        "dup_product_skin_type": dup_key,
        "null_base_skin_type": null_base,
        "zero_skin_review_count": zero_skin,
        "skin_count_mismatch": skin_sum_mismatch,
        "overall_count_mismatch": overall_sum_mismatch,
        "max_skin_rate_deviation": skin_rate_dev,
        "max_overall_rate_deviation": overall_rate_dev,
    }


# ── Section 6: Save Parquet ───────────────────────────────────────────────────

def save_parquet(result: pd.DataFrame) -> int:
    print(f"\n[6] parquet 저장: {OUTPUT_PARQUET}")
    result.to_parquet(OUTPUT_PARQUET, index=False)
    reloaded = pd.read_parquet(OUTPUT_PARQUET)
    if len(reloaded) != len(result):
        _critical(f"재로드 row 수 불일치: 저장 {len(result)}, 재로드 {len(reloaded)}")
    print(f"  저장/재로드 row 수: {len(reloaded):,} (일치)")
    return len(reloaded)


# ── Section 7: Preview CSV ────────────────────────────────────────────────────

def save_preview_csv(result: pd.DataFrame) -> int:
    print(f"\n[7] preview CSV 저장: {OUTPUT_PREVIEW}")

    def to_csv_df(sub: pd.DataFrame) -> pd.DataFrame:
        d = sub.copy()
        d["top_skin_need_tags"] = d["top_skin_need_tags"].apply(_tags_to_str)
        d["top_skin_concern_tags"] = d["top_skin_concern_tags"].apply(_tags_to_str)
        return d

    parts = [
        result.nlargest(25, "skin_review_count"),
        result.nsmallest(25, "skin_review_count"),
        result[result["skin_review_count"] >= 5].nlargest(25, "skin_negative_rate"),
        result[result["skin_review_count"] >= 5].nsmallest(25, "skin_negative_rate"),
        result[result["caution_level"] == "high_negative_signal"].head(25),
        result[result["caution_level"] == "moderate_negative_signal"].head(25),
        result[result["caution_level"] == "insufficient_evidence"].head(25),
        result[result["caution_level"] == "normal"].head(25),
    ]
    for st in SKIN_TYPES:
        parts.append(result[result["base_skin_type"] == st].head(10))
    # [1] platform 샘플: musinsa / oliveyoung만 (coupang은 product_skin_aggregates에 없음)
    for plat in ["musinsa", "oliveyoung"]:
        parts.append(result[result["platform"] == plat].head(25))

    preview = pd.concat(parts).drop_duplicates(subset=["product_key", "base_skin_type"]).head(200)
    to_csv_df(preview).to_csv(OUTPUT_PREVIEW, index=False, encoding="utf-8-sig")
    print(f"  preview row 수: {len(preview):,}")
    return len(preview)


# ── Section 8: Reports ────────────────────────────────────────────────────────

def _top20_table(df: pd.DataFrame, sort_col: str, ascending: bool = False,
                 filter_expr: str | None = None, n: int = 20) -> list[dict]:
    sub = df.copy()
    if filter_expr:
        sub = sub.query(filter_expr)
    sub = sub.sort_values(sort_col, ascending=ascending).head(n)
    cols = ["product_key", "product_name", "brand", "base_skin_type", sort_col]
    return sub[cols].to_dict("records")


def build_report(result: pd.DataFrame, load_stats: dict, skin_stats: dict,
                 validation_stats: dict, reloaded_rows: int) -> None:
    print(f"\n[8] 리포트 생성")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_products = int(result["product_key"].nunique())
    n_products_overall = load_stats["product_key_count"]

    # by skin type
    by_skin: dict[str, dict] = {}
    for st in SKIN_TYPES:
        sub = result[result["base_skin_type"] == st]
        if len(sub) == 0:
            continue
        by_skin[st] = {
            "row_count": len(sub),
            "total_review_count": int(sub["skin_review_count"].sum()),
            "positive_count": int(sub["skin_positive_count"].sum()),
            "neutral_count": int(sub["skin_neutral_count"].sum()),
            "negative_count": int(sub["skin_negative_count"].sum()),
            "positive_rate": round(float(sub["skin_positive_count"].sum() /
                                         sub["skin_review_count"].sum()), 4),
            "neutral_rate": round(float(sub["skin_neutral_count"].sum() /
                                        sub["skin_review_count"].sum()), 4),
            "negative_rate": round(float(sub["skin_negative_count"].sum() /
                                         sub["skin_review_count"].sum()), 4),
            "avg_skin_review_count": round(float(sub["skin_review_count"].mean()), 2),
            "high_negative_signal_products": int(
                (sub["caution_level"] == "high_negative_signal").sum()
            ),
            "insufficient_evidence_products": int(
                (sub["caution_level"] == "insufficient_evidence").sum()
            ),
        }

    # by platform
    by_platform: dict[str, dict] = {}
    for plat, grp in result.groupby("platform"):
        by_platform[str(plat)] = {
            "product_key_count": int(grp["product_key"].nunique()),
            "skin_aggregate_rows": len(grp),
        }
    # coupang별도: overall에서는 있지만 skin에는 없음
    all_platforms_overall = load_stats.get("platforms_overall", {})

    caution_dist = result["caution_level"].value_counts().to_dict()
    confidence_dist = result["skin_confidence_label"].value_counts().to_dict()

    top_products = {
        "by_total_review_count": _top20_table(
            result.drop_duplicates("product_key"), "total_review_count"
        ),
        "by_skin_review_count": _top20_table(result, "skin_review_count"),
        "by_skin_negative_rate_all": _top20_table(result, "skin_negative_rate"),
        "by_skin_negative_rate_min5": _top20_table(
            result, "skin_negative_rate", filter_expr="skin_review_count >= 5"
        ),
        "by_skin_negative_rate_min20": _top20_table(
            result, "skin_negative_rate", filter_expr="skin_review_count >= 20"
        ),
    }

    report_json = {
        "generated_at": now,
        "service_reviews": load_stats,
        "overall": {
            "product_count_in_service_reviews": n_products_overall,
            "product_count_in_skin_aggregates": n_products,
        },
        "skin_aggregates": {
            "row_count": len(result),
            "reloaded_row_count": reloaded_rows,
            "by_skin_type": by_skin,
            "by_platform_in_skin_aggregates": by_platform,
            "caution_level_dist": {str(k): int(v) for k, v in caution_dist.items()},
            "confidence_label_dist": {str(k): int(v) for k, v in confidence_dist.items()},
            "skin_reviews_used": skin_stats["skin_reviews_used"],
            "skin_reviews_excluded": skin_stats["skin_reviews_excluded"],
            "exclusion_breakdown": {
                "base_skin_type_missing": skin_stats["excl_base_skin_type_missing"],
                "no_base_skin_type": skin_stats["excl_no_base_skin_type"],
                "predicted_sentiment_null": skin_stats["excl_null_sentiment"],
            },
        },
        "top_products": top_products,
        "validation": validation_stats,
    }

    REPORT_JSON.write_text(
        json.dumps(report_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  JSON 저장: {REPORT_JSON}")

    # ── MD ────────────────────────────────────────────────────────────────────
    skin_used = skin_stats["skin_reviews_used"]
    skin_excl = skin_stats["skin_reviews_excluded"]
    excl_miss = skin_stats["excl_base_skin_type_missing"]
    excl_nb = skin_stats["excl_no_base_skin_type"]
    excl_ns = skin_stats["excl_null_sentiment"]

    def fmt_top20_md(records: list[dict], sort_col: str) -> str:
        if not records:
            return "_없음_\n"
        lines = [f"| 순위 | product_key | product_name | brand | base_skin_type | {sort_col} |",
                 "|-----|------------|-------------|-------|---------------|---------|"]
        for i, r in enumerate(records, 1):
            name = str(r.get("product_name", ""))[:25]
            brand = str(r.get("brand", ""))[:15]
            val = r.get(sort_col, "")
            if isinstance(val, float):
                val = f"{val:.4f}"
            lines.append(f"| {i} | {r['product_key']} | {name} | {brand} "
                         f"| {r.get('base_skin_type', '-')} | {val} |")
        return "\n".join(lines) + "\n"

    def skin_type_table() -> str:
        rows = ["| 피부 타입 | row 수 | 리뷰 수 | positive | neutral | negative "
                "| pos_rate | neg_rate | avg_review | high_neg | insuf |",
                "|----------|--------|--------|---------|--------|---------|"
                "--------|--------|----------|---------|-------|"]
        for st, d in by_skin.items():
            rows.append(
                f"| {st} | {d['row_count']} | {d['total_review_count']:,} "
                f"| {d['positive_count']:,} | {d['neutral_count']:,} | {d['negative_count']:,} "
                f"| {d['positive_rate']:.3f} | {d['negative_rate']:.3f} "
                f"| {d['avg_skin_review_count']:.1f} "
                f"| {d['high_negative_signal_products']} | {d['insufficient_evidence_products']} |"
            )
        return "\n".join(rows) + "\n"

    caution_str = "  \n".join(f"- {k}: {v}" for k, v in sorted(caution_dist.items(), key=lambda x: -x[1]))
    confidence_str = "  \n".join(f"- {k}: {v}" for k, v in sorted(confidence_dist.items(), key=lambda x: -x[1]))

    plat_rows = "\n".join(
        f"| {p} | {d['product_key_count']} | {d['skin_aggregate_rows']} |"
        for p, d in by_platform.items()
    )

    vstat = validation_stats
    md = textwrap.dedent(f"""\
    # product_skin_aggregates 검증 리포트

    생성 일시: {now}

    ---

    ## 1. 기본 수치 요약

    | 항목 | 수치 |
    |------|------|
    | service_reviews row 수 | {load_stats['row_count']:,} |
    | service_reviews product_key 수 | {n_products_overall:,} |
    | 전체 상품 집계 product 수 | {n_products_overall:,} |
    | 피부 타입별 집계 row 수 | {len(result):,} |
    | 피부 타입별 집계 product 수 | {n_products:,} |
    | 피부 타입 집계 사용 리뷰 수 | {skin_used:,} |
    | 피부 타입 집계 제외 리뷰 수 | {skin_excl:,} |
    | product_skin_aggregates.parquet 재로드 row 수 | {reloaded_rows:,} |

    ### 제외 사유별 수

    | 사유 | 건수 |
    |------|------|
    | base_skin_type missing (skin_type_normalization_status == missing) | {excl_miss:,} |
    | no_base_skin_type (831건) | {excl_nb} |
    | predicted_sentiment null | {excl_ns} |

    ---

    ## 2. 피부 타입별 집계 수치

    {skin_type_table()}

    ### caution_level 분포
    {caution_str}

    ### confidence_label 분포
    {confidence_str}

    ---

    ## 3. 플랫폼별 수치

    | platform | product_skin_aggregates product 수 | skin aggregate row 수 |
    |----------|-----------------------------------|-----------------------|
    {plat_rows}

    > **coupang 확인**: coupang은 base_skin_type 데이터가 없으므로 product_skin_aggregates에 포함되지 않는 것이 정상.
    > 위 테이블에 coupang이 없으면 정상.
    >
    > **musinsa / oliveyoung 확인**: 위 테이블에 포함되어 있으면 정상.

    ---

    ## 4. 상위 상품 테이블

    ### 4-1. total_review_count 상위 20 (전체 상품 기준)
    {fmt_top20_md(top_products['by_total_review_count'], 'total_review_count')}

    ### 4-2. skin_review_count 상위 20
    {fmt_top20_md(top_products['by_skin_review_count'], 'skin_review_count')}

    ### 4-3. skin_negative_rate 상위 20 (전체)
    {fmt_top20_md(top_products['by_skin_negative_rate_all'], 'skin_negative_rate')}

    ### 4-4. skin_negative_rate 상위 20 (skin_review_count >= 5)
    {fmt_top20_md(top_products['by_skin_negative_rate_min5'], 'skin_negative_rate')}

    ### 4-5. skin_negative_rate 상위 20 (skin_review_count >= 20)
    {fmt_top20_md(top_products['by_skin_negative_rate_min20'], 'skin_negative_rate')}

    ---

    ## 5. 품질 검증 결과

    | 검증 항목 | 결과 | 판단 |
    |----------|------|------|
    | (product_key, base_skin_type) 중복 | {vstat['dup_product_skin_type']} | {'OK' if vstat['dup_product_skin_type'] == 0 else 'CRITICAL'} |
    | base_skin_type null | {vstat['null_base_skin_type']} | {'OK' if vstat['null_base_skin_type'] == 0 else 'CRITICAL'} |
    | skin_review_count <= 0 | {vstat['zero_skin_review_count']} | {'OK' if vstat['zero_skin_review_count'] == 0 else 'CRITICAL'} |
    | skin count 합계 불일치 | {vstat['skin_count_mismatch']} | {'OK' if vstat['skin_count_mismatch'] == 0 else 'CRITICAL'} |
    | overall count 합계 불일치 | {vstat['overall_count_mismatch']} | {'OK' if vstat['overall_count_mismatch'] == 0 else 'CRITICAL'} |
    | skin rate 합계 최대 편차 | {vstat['max_skin_rate_deviation']:.2e} | {'OK' if vstat['max_skin_rate_deviation'] <= 0.001 else 'WARNING'} |
    | overall rate 합계 최대 편차 | {vstat['max_overall_rate_deviation']:.2e} | {'OK' if vstat['max_overall_rate_deviation'] <= 0.001 else 'WARNING'} |
    | parquet 재로드 row 수 일치 | {reloaded_rows} == {len(result)} | {'OK' if reloaded_rows == len(result) else 'CRITICAL'} |

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

    - 직접 확인한 샘플 수: _(스크립트 실행 후 채움)_
    - 확인한 파일: reports/product_skin_aggregates_manual_review_samples.csv
    - 샘플링 그룹: aggregate_count_check / high_negative_signal / insufficient_evidence / normal / base_skin_type × 5 / platform × 2 / skin_need_tag / skin_concern_tag
    - aggregate count 검증 결과: _(채움)_
    - high negative signal 샘플 판단: _(실제 review_text 확인 후 채움)_
    - insufficient evidence 샘플 판단: _(채움)_
    - platform 샘플 판단: _(채움)_
    - 정상으로 판단한 예시: _(채움)_
    - 이상하거나 애매한 예시: _(채움)_
    - 수정한 규칙: _(채움)_
    - 아직 남은 위험: _(채움)_
    - Step 4 진행 가능 여부: _(채움)_
    """)

    REPORT_MD.write_text(md, encoding="utf-8")
    print(f"  MD 저장: {REPORT_MD}")


# ── Section 9: Manual Review Samples ─────────────────────────────────────────

def _make_sample_row(row: pd.Series, group: str, note: str = "") -> dict:
    d = {
        "sample_group": group,
        "product_key": row["product_key"],
        "platform": row["platform"],
        "product_id": row["product_id"],
        "product_name": row["product_name"],
        "brand": row["brand"],
        "category": row["category"],
        "base_skin_type": row["base_skin_type"],
        "total_review_count": row["total_review_count"],
        "skin_review_count": row["skin_review_count"],
        "skin_positive_count": row["skin_positive_count"],
        "skin_neutral_count": row["skin_neutral_count"],
        "skin_negative_count": row["skin_negative_count"],
        "skin_positive_rate": round(float(row["skin_positive_rate"]), 4),
        "skin_neutral_rate": round(float(row["skin_neutral_rate"]), 4),
        "skin_negative_rate": round(float(row["skin_negative_rate"]), 4),
        "skin_confidence_label": row["skin_confidence_label"],
        "caution_level": row["caution_level"],
        "caution_message": row["caution_message"],
        "top_skin_need_tags": _tags_to_str(row["top_skin_need_tags"]),
        "top_skin_concern_tags": _tags_to_str(row["top_skin_concern_tags"]),
        "skin_concern_code_count": row["skin_concern_code_count"],
        "manual_check_note": note,
    }
    return d


def build_manual_review_samples(result: pd.DataFrame, df: pd.DataFrame) -> None:
    print(f"\n[9] 수동 검수 샘플 생성")
    samples: list[dict] = []

    # ── 1. aggregate_count_check_samples ──────────────────────────────────────
    print("  그룹 1: aggregate_count_check_samples (20개)")
    check_rows = result.sample(min(20, len(result)), random_state=42)
    for _, row in check_rows.iterrows():
        pk = row["product_key"]
        bst = row["base_skin_type"]
        orig = df[
            (df["product_key"] == pk) &
            (df["base_skin_type"] == bst) &
            (df["predicted_sentiment"].notna())
        ]
        orig_n = len(orig)
        orig_pos = int((orig["predicted_sentiment"] == "positive").sum())
        orig_neu = int((orig["predicted_sentiment"] == "neutral").sum())
        orig_neg = int((orig["predicted_sentiment"] == "negative").sum())
        match = (
            orig_n == row["skin_review_count"] and
            orig_pos == row["skin_positive_count"] and
            orig_neu == row["skin_neutral_count"] and
            orig_neg == row["skin_negative_count"]
        )
        note = (
            f"원본재필터: n={orig_n} pos={orig_pos} neu={orig_neu} neg={orig_neg} "
            f"| 집계: n={row['skin_review_count']} pos={row['skin_positive_count']} "
            f"neu={row['skin_neutral_count']} neg={row['skin_negative_count']} "
            f"| {'일치' if match else 'MISMATCH!'}"
        )
        samples.append(_make_sample_row(row, "aggregate_count_check_samples", note))

    # ── 2. high_negative_signal_samples ──────────────────────────────────────
    print("  그룹 2: high_negative_signal_samples (최소 20개)")
    hns = result[result["caution_level"] == "high_negative_signal"].copy()
    hns_n = len(hns)
    print(f"    가용 row 수: {hns_n}")
    hns_sample = hns.head(min(30, hns_n))
    for _, row in hns_sample.iterrows():
        pk = row["product_key"]
        bst = row["base_skin_type"]
        neg_reviews = df[
            (df["product_key"] == pk) &
            (df["base_skin_type"] == bst) &
            (df["predicted_sentiment"] == "negative")
        ]
        if len(neg_reviews) > 0:
            sample_text = str(neg_reviews.iloc[0]["review_text"])[:120].replace("\n", " ")
            note = f"neg_review_text 샘플: [{sample_text}]"
        else:
            note = "negative review_text 없음 (예상치 못한 상황)"
        samples.append(_make_sample_row(row, "high_negative_signal_samples", note))
    if hns_n < 20:
        print(f"    [INFO] high_negative_signal row가 {hns_n}개뿐 — 가능한 만큼 포함")

    # ── 3. insufficient_evidence_samples ─────────────────────────────────────
    print("  그룹 3: insufficient_evidence_samples (최소 20개)")
    ie = result[result["caution_level"] == "insufficient_evidence"].head(20)
    for _, row in ie.iterrows():
        note = f"skin_review_count={row['skin_review_count']} (0~4이면 정상)"
        samples.append(_make_sample_row(row, "insufficient_evidence_samples", note))

    # ── 4. normal_samples ────────────────────────────────────────────────────
    print("  그룹 4: normal_samples (20개)")
    nm = result[result["caution_level"] == "normal"].head(20)
    for _, row in nm.iterrows():
        samples.append(_make_sample_row(row, "normal_samples",
                                        f"neg_rate={row['skin_negative_rate']:.3f}"))

    # ── 5. base_skin_type_samples ─────────────────────────────────────────────
    print("  그룹 5: base_skin_type_samples (각 최소 20개)")
    for st in SKIN_TYPES:
        sub = result[result["base_skin_type"] == st].head(20)
        for _, row in sub.iterrows():
            samples.append(_make_sample_row(row, f"base_skin_type_{st}",
                                            f"base_skin_type={st} 확인"))

    # ── 6. platform_samples (musinsa / oliveyoung만) ───────────────────────────
    print("  그룹 6: platform_samples (musinsa/oliveyoung 각 20개)")
    for plat in ["musinsa", "oliveyoung"]:
        sub = result[result["platform"] == plat].head(20)
        n_found = len(sub)
        for _, row in sub.iterrows():
            samples.append(_make_sample_row(
                row, f"platform_{plat}",
                f"platform={plat} 확인 ({n_found}개 가용)"
            ))
    # coupang 부재 확인 항목을 별도 행으로 추가
    coupang_in_agg = len(result[result["platform"] == "coupang"])
    samples.append({
        col: "" for col in MANUAL_COLS
    })
    samples[-1].update({
        "sample_group": "platform_coupang_absence_check",
        "manual_check_note": (
            f"coupang product_skin_aggregates row 수: {coupang_in_agg} "
            f"({'정상 (0건)' if coupang_in_agg == 0 else 'ABNORMAL: coupang이 포함되어 있음!'})"
        ),
    })

    # ── 7. skin_need_tag_samples ──────────────────────────────────────────────
    print("  그룹 7: skin_need_tag_samples (20개)")
    has_need = result[result["top_skin_need_tags"].apply(
        lambda x: len(arr_to_list(x)) > 0
    )].head(20)
    for _, row in has_need.iterrows():
        note = f"top_skin_need_tags: {_tags_to_str(row['top_skin_need_tags'])}"
        samples.append(_make_sample_row(row, "skin_need_tag_samples", note))

    # ── 8. skin_concern_tag_samples ───────────────────────────────────────────
    print("  그룹 8: skin_concern_tag_samples (20개)")
    has_concern = result[result["top_skin_concern_tags"].apply(
        lambda x: len(arr_to_list(x)) > 0
    )].head(20)
    for _, row in has_concern.iterrows():
        note = f"top_skin_concern_tags: {_tags_to_str(row['top_skin_concern_tags'])}"
        samples.append(_make_sample_row(row, "skin_concern_tag_samples", note))

    # ── Save CSV ──────────────────────────────────────────────────────────────
    sample_df = pd.DataFrame(samples, columns=MANUAL_COLS)
    sample_df.to_csv(MANUAL_CSV, index=False, encoding="utf-8-sig")
    print(f"  CSV 저장: {MANUAL_CSV} ({len(sample_df):,} rows)")

    # ── Save MD ───────────────────────────────────────────────────────────────
    _save_manual_md(sample_df)


def _save_manual_md(sample_df: pd.DataFrame) -> None:
    groups = sample_df["sample_group"].unique()
    sections = []
    for grp in groups:
        sub = sample_df[sample_df["sample_group"] == grp]
        header = f"## {grp} ({len(sub)}행)\n"
        if len(sub) == 1 and sub.iloc[0]["product_key"] == "":
            # 특수 체크 행
            note = sub.iloc[0]["manual_check_note"]
            sections.append(header + f"\n{note}\n")
            continue
        rows = [
            "| product_name | brand | base_skin_type | skin_n | neg_rate "
            "| caution_level | manual_check_note |",
            "|-------------|-------|---------------|--------|---------|"
            "-------------|------------------|",
        ]
        for _, r in sub.iterrows():
            name = str(r["product_name"])[:20]
            brand = str(r["brand"])[:12]
            note = str(r["manual_check_note"])[:80]
            rows.append(
                f"| {name} | {brand} | {r['base_skin_type']} "
                f"| {r['skin_review_count']} | {r['skin_negative_rate']:.3f} "
                f"| {r['caution_level']} | {note} |"
            )
        sections.append(header + "\n" + "\n".join(rows) + "\n")

    md = "# 수동 검수 샘플 — product_skin_aggregates\n\n"
    md += "\n---\n\n".join(sections)
    MANUAL_MD.write_text(md, encoding="utf-8")
    print(f"  MD 저장: {MANUAL_MD}")


# ── Section 10: Worklog Update ────────────────────────────────────────────────

def update_worklog(result: pd.DataFrame, load_stats: dict, skin_stats: dict,
                   validation_stats: dict) -> None:
    print(f"\n[10] worklog 업데이트: {WORKLOG}")
    now_str = datetime.now().strftime("%H:%M")
    n_rows = len(result)
    caution_dist = result["caution_level"].value_counts().to_dict()

    entry = f"""

---

## Step 3 — product_skin_aggregates 생성

### {now_str} - Step 3: 상품별/피부타입별 집계 테이블 생성

#### What changed

- `scripts/build_product_skin_aggregates.py` 신규 작성
- `preprocessed_v3/product_skin_aggregates.parquet` 생성 ({n_rows:,} rows)
- `preprocessed_v3/product_skin_aggregates_preview.csv` 생성
- `reports/product_skin_aggregates_check.md/json` 생성
- `reports/product_skin_aggregates_manual_review_samples.csv/md` 생성

#### Why

- MVP 피부 타입 기반 부정 리뷰 탐색 서비스 Step 3
- service_reviews.parquet를 기반으로 상품별/피부타입별 집계 → Step 4 추천 점수 산정 기반

#### Files touched

- `scripts/build_product_skin_aggregates.py` - 신규
- `preprocessed_v3/product_skin_aggregates.parquet` - 신규
- `preprocessed_v3/product_skin_aggregates_preview.csv` - 신규
- `reports/product_skin_aggregates_check.md` - 신규
- `reports/product_skin_aggregates_check.json` - 신규
- `reports/product_skin_aggregates_manual_review_samples.csv` - 신규
- `reports/product_skin_aggregates_manual_review_samples.md` - 신규

#### 핵심 집계 결과

| 항목 | 수치 |
|------|------|
| service_reviews row 수 | {load_stats['row_count']:,} |
| 전체 product_key 수 | {load_stats['product_key_count']:,} |
| 피부 타입별 집계 row 수 | {n_rows:,} |
| 피부 타입 집계 사용 리뷰 수 | {skin_stats['skin_reviews_used']:,} |
| 피부 타입 집계 제외 리뷰 수 | {skin_stats['skin_reviews_excluded']:,} |
| (product_key, base_skin_type) 중복 | {validation_stats['dup_product_skin_type']} |
| base_skin_type null | {validation_stats['null_base_skin_type']} |
| skin count 합계 불일치 | {validation_stats['skin_count_mismatch']} |
| overall count 합계 불일치 | {validation_stats['overall_count_mismatch']} |

#### caution_level 분포

{chr(10).join(f'- {k}: {v}' for k, v in sorted(caution_dist.items(), key=lambda x: -x[1]))}

#### Decisions

- Decision: caution_level 분류 기준 — skin_review_count < 5: insufficient_evidence, neg_rate >= 0.25: high_negative_signal, >= 0.15: moderate_negative_signal
  - Reason: MVP 서비스 방향 — 부정 신호를 강하게 노출, 근거 부족 상품은 명확히 표시
  - Alternatives considered: 절대 수 기준 (e.g. negative_count >= 3)
  - Why rejected: 비율 기반이 리뷰 수 차이를 중립화하므로 더 공정

- Decision: coupang은 피부 타입 집계에서 제외 (전체 집계에는 포함)
  - Reason: coupang 리뷰에 base_skin_type 데이터 없음

#### Commands / Tests

```bash
C:\\Users\\user\\anaconda3\\envs\\oliveyoung\\python.exe scripts/build_product_skin_aggregates.py
```

#### Verification

- [x] critical 검증 (중복, null, count 합계) 모두 통과
- [x] parquet 재로드 row 수 일치
- [x] 수동 검수 샘플 생성 완료
- [ ] 수동 검수 결과 리포트 반영 (별도 진행)

#### Remaining work

- 수동 검수 샘플 직접 확인 후 reports/product_skin_aggregates_check.md 수동 섹션 업데이트
- Step 4: 추천 점수 계산

#### Risks / Notes

- predicted_sentiment는 BiLSTM v3 예측값 (macro_f1 0.666) — neutral 신뢰도 낮음
- C09/C10 코드 의미 불명 — UI 직접 노출 금지
"""
    existing = WORKLOG.read_text(encoding="utf-8")
    WORKLOG.write_text(existing + entry, encoding="utf-8")
    print("  worklog 업데이트 완료")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    t_start = time.time()
    print("=" * 60)
    print("Step 3: product_skin_aggregates 생성")
    print(f"시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # [3] aggregation.py 함수 존재 확인
    required_funcs = [
        "get_confidence_label", "safe_rate", "get_caution_level",
        "get_caution_message", "arr_to_list", "collect_top_tags",
    ]
    import recommendation.aggregation as _agg_mod
    missing = [f for f in required_funcs if not hasattr(_agg_mod, f)]
    if missing:
        _critical(f"recommendation/aggregation.py에 다음 함수가 없음: {missing}")
    print(f"[OK] recommendation/aggregation.py 필수 함수 {len(required_funcs)}개 확인")

    df, load_stats = load_and_validate()
    overall = build_overall_aggregates(df)
    skin_agg, skin_stats = build_skin_aggregates(df)
    result = build_final(skin_agg, overall)
    validation_stats = validate_result(result)
    reloaded_rows = save_parquet(result)
    save_preview_csv(result)
    build_report(result, load_stats, skin_stats, validation_stats, reloaded_rows)
    build_manual_review_samples(result, df)
    update_worklog(result, load_stats, skin_stats, validation_stats)

    elapsed = time.time() - t_start
    print("\n" + "=" * 60)
    print("완료")
    print(f"소요 시간: {elapsed:.1f}s")
    print("=" * 60)
    print("\n### Step 3 최종 요약 ###")
    print(f"  service_reviews row 수: {load_stats['row_count']:,}")
    print(f"  전체 product_key 수: {load_stats['product_key_count']:,}")
    print(f"  피부 타입별 집계 row 수: {len(result):,}")
    print(f"  parquet 재로드 row 수: {reloaded_rows:,}")
    print(f"  (product_key, base_skin_type) 중복: {validation_stats['dup_product_skin_type']}")
    print(f"  base_skin_type null: {validation_stats['null_base_skin_type']}")
    print(f"  skin count 합계 불일치: {validation_stats['skin_count_mismatch']}")
    print(f"  overall count 합계 불일치: {validation_stats['overall_count_mismatch']}")
    caution_dist = result["caution_level"].value_counts().to_dict()
    print(f"  caution_level 분포: {caution_dist}")
    platforms_in_agg = result["platform"].unique().tolist()
    coupang_in_agg = len(result[result["platform"] == "coupang"])
    print(f"  product_skin_aggregates의 platform: {platforms_in_agg}")
    print(f"  coupang row 수 (0이면 정상): {coupang_in_agg}")


if __name__ == "__main__":
    main()
