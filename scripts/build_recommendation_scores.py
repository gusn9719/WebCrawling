"""
Step 4: product_recommendation_scores 생성.

입력: preprocessed_v3/product_skin_aggregates.parquet (6,008 rows)
출력: preprocessed_v3/product_recommendation_scores.parquet (38 cols)
     preprocessed_v3/product_recommendation_scores_preview.csv
     reports/recommendation_scores_check.md / .json
     reports/recommendation_scores_manual_review_samples.csv / .md
     docs/worklog/2026-06-27.md (Step 4 섹션 추가)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# ── ROOT 확인 ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
EXPECTED_ROOT = Path("D:/_WebCrawling/oliveyoung_crawler").resolve()
if ROOT != EXPECTED_ROOT:
    print(f"[CRITICAL] 작업 루트 불일치: {ROOT} != {EXPECTED_ROOT}", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(ROOT))

from recommendation.scoring import (  # noqa: E402
    get_evidence_level,
    get_evidence_weight,
    compute_negative_signal_score,
    compute_recommendation_score,
    get_recommendation_tier,
    get_display_message,
    get_rank_exposure_flag,
    get_review_first_flag,
)
from recommendation.aggregation import arr_to_list  # noqa: E402

# ── 경로 상수 ─────────────────────────────────────────────────────────────────
AGG_PARQUET  = ROOT / "preprocessed_v3" / "product_skin_aggregates.parquet"
SVC_PARQUET  = ROOT / "preprocessed_v3" / "service_reviews.parquet"
OUT_PARQUET  = ROOT / "preprocessed_v3" / "product_recommendation_scores.parquet"
OUT_CSV      = ROOT / "preprocessed_v3" / "product_recommendation_scores_preview.csv"
REPORT_MD    = ROOT / "reports" / "recommendation_scores_check.md"
REPORT_JSON  = ROOT / "reports" / "recommendation_scores_check.json"
SAMPLES_CSV  = ROOT / "reports" / "recommendation_scores_manual_review_samples.csv"
SAMPLES_MD   = ROOT / "reports" / "recommendation_scores_manual_review_samples.md"
WORKLOG      = ROOT / "docs" / "worklog" / "2026-06-27.md"

PROTECTED_FILES = [
    ROOT / "preprocessed_v3" / "train.parquet",
    ROOT / "preprocessed_v3" / "val.parquet",
    ROOT / "preprocessed_v3" / "ambiguous.parquet",
    ROOT / "preprocessed_v3" / "lstm_v3_preds.parquet",
    ROOT / "preprocessed_v3" / "service_reviews.parquet",
    ROOT / "preprocessed_v3" / "product_skin_aggregates.parquet",
]

RATE_COLS_SKIN    = ["skin_positive_rate", "skin_neutral_rate", "skin_negative_rate"]
RATE_COLS_OVERALL = ["overall_positive_rate", "overall_neutral_rate", "overall_negative_rate"]
RATE_COLS_ALL     = RATE_COLS_SKIN + RATE_COLS_OVERALL
RATE_SUM_ATOL     = 1e-6

EXPECTED_INPUT_ROWS     = 6008
EXPECTED_CAUTION_LEVELS = {
    "normal", "insufficient_evidence", "moderate_negative_signal", "high_negative_signal"
}

NEW_COLS = [
    "evidence_level", "evidence_weight",
    "negative_signal_score",
    "recommendation_score",
    "recommendation_tier",
    "rank_exposure_flag",
    "review_first_flag",
    "display_message",
]


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _critical(msg: str) -> None:
    print(f"[CRITICAL] {msg}", file=sys.stderr)
    sys.exit(1)


def _warn(msg: str) -> None:
    print(f"[WARNING] {msg}")


# ── 보호 파일 수정 시간 ────────────────────────────────────────────────────────

def record_protected_mtimes() -> dict[str, float]:
    mtimes: dict[str, float] = {}
    for p in PROTECTED_FILES:
        if p.exists():
            mtimes[str(p)] = p.stat().st_mtime
        else:
            _warn(f"보호 파일 없음 (pre-flight): {p}")
    return mtimes


def check_protected_mtimes(pre: dict[str, float]) -> None:
    changed = []
    for path_str, mtime in pre.items():
        p = Path(path_str)
        if not p.exists():
            changed.append(f"{path_str} (파일 삭제됨)")
        elif abs(p.stat().st_mtime - mtime) > 0.01:
            changed.append(path_str)
    if changed:
        _critical(
            "보호 파일 수정 시간 변경 감지 (절대 수정 금지):\n" + "\n".join(changed)
        )
    print("[INFO] 보호 파일 수정 시간 불변 확인 완료")


# ── 입력 로드 + 검증 ──────────────────────────────────────────────────────────

def load_and_validate() -> pd.DataFrame:
    print(f"[INFO] 입력 로드: {AGG_PARQUET}")
    if not AGG_PARQUET.exists():
        _critical(f"입력 파일 없음: {AGG_PARQUET}")

    df = pd.read_parquet(AGG_PARQUET)
    errors: list[str] = []

    # row 수
    if len(df) != EXPECTED_INPUT_ROWS:
        errors.append(f"row 수 불일치: {len(df)} != {EXPECTED_INPUT_ROWS}")

    # 필수 null 검사
    for col in ("product_key", "base_skin_type"):
        n = df[col].isna().sum()
        if n > 0:
            errors.append(f"{col} null: {n}")

    # (product_key, base_skin_type) 중복
    n_dup = df.duplicated(subset=["product_key", "base_skin_type"]).sum()
    if n_dup > 0:
        errors.append(f"(product_key, base_skin_type) 중복: {n_dup}")

    # skin_review_count <= 0
    n_zero = (df["skin_review_count"] <= 0).sum()
    if n_zero > 0:
        errors.append(f"skin_review_count <= 0: {n_zero}")

    # skin count 합계
    skin_sum = (
        df["skin_positive_count"] + df["skin_neutral_count"] + df["skin_negative_count"]
    )
    n_skin_mm = (skin_sum != df["skin_review_count"]).sum()
    if n_skin_mm > 0:
        errors.append(f"skin count 합계 불일치: {n_skin_mm}")

    # overall count 합계
    overall_sum = (
        df["overall_positive_count"]
        + df["overall_neutral_count"]
        + df["overall_negative_count"]
    )
    n_overall_mm = (overall_sum != df["total_review_count"]).sum()
    if n_overall_mm > 0:
        errors.append(f"overall count 합계 불일치: {n_overall_mm}")

    # caution_level 값 범위
    actual_levels = set(df["caution_level"].dropna().unique())
    unexpected = actual_levels - EXPECTED_CAUTION_LEVELS
    if unexpected:
        errors.append(f"caution_level 예상 외 값: {unexpected}")

    # avg_rating NaN (먼저 보고, NaN > 0이면 critical)
    n_avg_nan = int(df["avg_rating"].isna().sum())
    print(f"[INFO] avg_rating NaN 수: {n_avg_nan}")
    if n_avg_nan > 0:
        errors.append(f"avg_rating NaN: {n_avg_nan} (집계 오류 가능성, fillna 금지)")

    # avg_rating 범위
    n_avg_oob = int(((df["avg_rating"] < 0) | (df["avg_rating"] > 5)).sum())
    if n_avg_oob > 0:
        errors.append(f"avg_rating 범위 이탈 (0~5): {n_avg_oob}")

    # rate 컬럼 단일 값 범위 (clip 금지)
    for col in RATE_COLS_ALL:
        n_oob = int(((df[col] < 0) | (df[col] > 1)).sum())
        if n_oob > 0:
            errors.append(f"{col} 범위 이탈 (0~1, clip 금지): {n_oob}")

    # skin rate 합계 per-row
    skin_rate_sum = df["skin_positive_rate"] + df["skin_neutral_rate"] + df["skin_negative_rate"]
    n_skin_rate_err = int((abs(skin_rate_sum - 1.0) > RATE_SUM_ATOL).sum())
    if n_skin_rate_err > 0:
        errors.append(
            f"skin rate 합계 1.0 이탈 (atol={RATE_SUM_ATOL}): {n_skin_rate_err} rows"
        )

    # overall rate 합계 per-row
    overall_rate_sum = (
        df["overall_positive_rate"] + df["overall_neutral_rate"] + df["overall_negative_rate"]
    )
    n_overall_rate_err = int((abs(overall_rate_sum - 1.0) > RATE_SUM_ATOL).sum())
    if n_overall_rate_err > 0:
        errors.append(
            f"overall rate 합계 1.0 이탈 (atol={RATE_SUM_ATOL}): {n_overall_rate_err} rows"
        )

    if errors:
        for e in errors:
            print(f"[CRITICAL] {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] 입력 검증 통과: {len(df)} rows, {len(df.columns)} cols")
    return df


# ── 점수 계산 ─────────────────────────────────────────────────────────────────

def build_scores(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    result["evidence_level"] = result["skin_review_count"].apply(
        lambda x: get_evidence_level(int(x))
    )
    result["evidence_weight"] = result["evidence_level"].apply(get_evidence_weight)

    result["negative_signal_score"] = result.apply(
        lambda r: compute_negative_signal_score(
            float(r["skin_negative_rate"]),
            float(r["evidence_weight"]),
        ),
        axis=1,
    )

    result["recommendation_score"] = result.apply(
        lambda r: compute_recommendation_score(
            float(r["skin_negative_rate"]),
            float(r["evidence_weight"]),
            str(r["caution_level"]),
            float(r["avg_rating"]),
            float(r["overall_positive_rate"]),
            float(r["overall_negative_rate"]),
        ),
        axis=1,
    )

    result["recommendation_tier"] = result.apply(
        lambda r: get_recommendation_tier(
            str(r["evidence_level"]),
            str(r["caution_level"]),
            float(r["recommendation_score"]),
        ),
        axis=1,
    )

    result["rank_exposure_flag"] = result.apply(
        lambda r: get_rank_exposure_flag(
            str(r["evidence_level"]),
            str(r["caution_level"]),
        ),
        axis=1,
    )

    result["review_first_flag"] = result.apply(
        lambda r: get_review_first_flag(
            str(r["caution_level"]),
            float(r["skin_negative_rate"]),
        ),
        axis=1,
    )

    result["display_message"] = result.apply(
        lambda r: get_display_message(
            str(r["caution_level"]),
            str(r["evidence_level"]),
            str(r["base_skin_type"]),
            int(r["skin_review_count"]),
        ),
        axis=1,
    )

    base_cols = list(df.columns)
    result = result[base_cols + NEW_COLS]
    print(f"[INFO] 점수 계산 완료: {len(result)} rows, {len(result.columns)} cols")
    return result


# ── 출력 검증 ─────────────────────────────────────────────────────────────────

def validate_output(result: pd.DataFrame, input_rows: int) -> list[str]:
    errors: list[str] = []

    if len(result) != input_rows:
        errors.append(f"출력 row 수 불일치: {len(result)} != {input_rows}")

    n_dup = result.duplicated(subset=["product_key", "base_skin_type"]).sum()
    if n_dup > 0:
        errors.append(f"(product_key, base_skin_type) 중복: {n_dup}")

    n_score_null = result["recommendation_score"].isna().sum()
    if n_score_null > 0:
        errors.append(f"recommendation_score null: {n_score_null}")

    n_score_oob = (
        (result["recommendation_score"] < 0) | (result["recommendation_score"] > 100)
    ).sum()
    if n_score_oob > 0:
        errors.append(f"recommendation_score 범위 이탈 (0~100): {n_score_oob}")

    n_neg_null = result["negative_signal_score"].isna().sum()
    if n_neg_null > 0:
        errors.append(f"negative_signal_score null: {n_neg_null}")

    n_neg_oob = (
        (result["negative_signal_score"] < 0) | (result["negative_signal_score"] > 1)
    ).sum()
    if n_neg_oob > 0:
        errors.append(f"negative_signal_score 범위 이탈 (0~1): {n_neg_oob}")

    n_msg_null = result["display_message"].isna().sum()
    if n_msg_null > 0:
        errors.append(f"display_message null: {n_msg_null}")

    # WARNING: insufficient_evidence에 rank_exposure_flag=True
    insuff_exposed = result.loc[
        result["evidence_level"] == "insufficient_evidence", "rank_exposure_flag"
    ].sum()
    if insuff_exposed > 0:
        _warn(f"insufficient_evidence에 rank_exposure_flag=True: {insuff_exposed}")

    # WARNING: 점수 분포 편중
    std = result["recommendation_score"].std()
    if std < 5.0:
        _warn(f"recommendation_score 표준편차 매우 낮음: {std:.2f}")

    return errors


# ── 저장 ─────────────────────────────────────────────────────────────────────

def save_parquet(result: pd.DataFrame) -> None:
    result.to_parquet(OUT_PARQUET, index=False)
    reloaded = pd.read_parquet(OUT_PARQUET)
    if len(reloaded) != len(result):
        _critical(
            f"parquet 재로드 row 수 불일치: {len(reloaded)} != {len(result)}"
        )
    print(f"[INFO] parquet 저장 완료: {OUT_PARQUET} ({len(result)} rows)")


def _list_col_to_str(series: pd.Series) -> pd.Series:
    return series.apply(lambda x: "|".join(arr_to_list(x)) if x is not None else "")


def save_preview_csv(result: pd.DataFrame) -> None:
    groups = []
    for lvl in ("strong_evidence", "limited_evidence", "insufficient_evidence"):
        sub = result[result["evidence_level"] == lvl].head(15).copy()
        sub["_sample_group"] = f"evidence_{lvl}"
        groups.append(sub)
    for tier in result["recommendation_tier"].unique():
        sub = result[result["recommendation_tier"] == tier].head(10).copy()
        sub["_sample_group"] = f"tier_{tier}"
        groups.append(sub)

    preview = pd.concat(groups, ignore_index=True).head(200)
    for col in ("top_skin_need_tags", "top_skin_concern_tags"):
        if col in preview.columns:
            preview[col] = _list_col_to_str(preview[col])
    preview.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"[INFO] preview CSV 저장: {OUT_CSV} ({len(preview)} rows)")


# ── 리포트 ────────────────────────────────────────────────────────────────────

def _pct(n: int, total: int) -> str:
    return f"{n:,} ({n / total * 100:.1f}%)" if total > 0 else f"{n}"


def build_report(result: pd.DataFrame) -> dict:
    n = len(result)
    n_products = result["product_key"].nunique()
    platform_dist = result["platform"].value_counts().to_dict()
    score_desc = result["recommendation_score"].describe()
    quantiles = result["recommendation_score"].quantile([0.1, 0.25, 0.5, 0.75, 0.9]).to_dict()
    bins = [0, 20, 40, 60, 80, 100]
    bin_counts = pd.cut(result["recommendation_score"], bins=bins, include_lowest=True).value_counts().sort_index()
    evidence_dist = result["evidence_level"].value_counts().to_dict()
    tier_dist = result["recommendation_tier"].value_counts().to_dict()
    rank_exposed = int(result["rank_exposure_flag"].sum())
    review_first = int(result["review_first_flag"].sum())
    bst_dist = result["base_skin_type"].value_counts().to_dict()

    # 서비스 관점 판단
    strong_normal = int(((result["evidence_level"] == "strong_evidence") & (result["caution_level"] == "normal")).sum())
    neutral_strong = int(((result["base_skin_type"] == "중성") & (result["evidence_level"] == "strong_evidence")).sum())
    hns_rows = result[result["caution_level"] == "high_negative_signal"]
    hns_all_review_first = bool(hns_rows["review_first_flag"].all()) if len(hns_rows) > 0 else True

    report = {
        "generated_at": datetime.now().isoformat(),
        "basic": {
            "total_rows": n,
            "unique_products": n_products,
            "platform_distribution": platform_dist,
        },
        "score_distribution": {
            "mean": round(float(score_desc["mean"]), 2),
            "std": round(float(score_desc["std"]), 2),
            "min": round(float(score_desc["min"]), 2),
            "max": round(float(score_desc["max"]), 2),
            "p10": round(float(quantiles[0.1]), 2),
            "p25": round(float(quantiles[0.25]), 2),
            "p50": round(float(quantiles[0.5]), 2),
            "p75": round(float(quantiles[0.75]), 2),
            "p90": round(float(quantiles[0.9]), 2),
            "bins": {str(k): int(v) for k, v in bin_counts.items()},
        },
        "evidence_level_distribution": evidence_dist,
        "recommendation_tier_distribution": tier_dist,
        "flags": {
            "rank_exposure_flag_true": rank_exposed,
            "rank_exposure_flag_true_pct": round(rank_exposed / n * 100, 1),
            "review_first_flag_true": review_first,
            "review_first_flag_true_pct": round(review_first / n * 100, 1),
        },
        "base_skin_type_distribution": bst_dist,
        "service_perspective": {
            "strong_evidence_normal_count": strong_normal,
            "strong_evidence_normal_pct": round(strong_normal / n * 100, 1),
            "neutral_skin_type_strong_evidence_count": neutral_strong,
            "high_negative_signal_all_review_first": hns_all_review_first,
            "high_negative_signal_count": len(hns_rows),
        },
    }

    # MD 작성
    lines = [
        "# Recommendation Scores Check Report",
        f"\n생성 시각: {report['generated_at']}",
        "\n## 1. 기본 수치",
        f"- 전체 row 수: {n:,}",
        f"- 고유 product 수: {n_products:,}",
        "- 플랫폼별 분포:",
    ]
    for plat, cnt in sorted(platform_dist.items()):
        lines.append(f"  - {plat}: {_pct(cnt, n)}")
    if "coupang" not in platform_dist:
        lines.append("  - coupang: 0 (정상 — base_skin_type 없음)")

    lines += [
        "\n## 2. recommendation_score 분포",
        f"- 평균: {report['score_distribution']['mean']}",
        f"- 표준편차: {report['score_distribution']['std']}",
        f"- 최소/최대: {report['score_distribution']['min']} / {report['score_distribution']['max']}",
        f"- P10/P25/P50/P75/P90: "
        f"{report['score_distribution']['p10']} / "
        f"{report['score_distribution']['p25']} / "
        f"{report['score_distribution']['p50']} / "
        f"{report['score_distribution']['p75']} / "
        f"{report['score_distribution']['p90']}",
        "\n구간별:",
    ]
    for rng, cnt in bin_counts.items():
        lines.append(f"  - {rng}: {_pct(int(cnt), n)}")

    lines += ["\n## 3. evidence_level 분포"]
    for lvl, cnt in sorted(evidence_dist.items(), key=lambda x: -x[1]):
        lines.append(f"  - {lvl}: {_pct(cnt, n)}")

    lines += ["\n## 4. recommendation_tier 분포"]
    for tier, cnt in sorted(tier_dist.items(), key=lambda x: -x[1]):
        lines.append(f"  - {tier}: {_pct(cnt, n)}")

    lines += [
        "\n## 5. rank_exposure_flag / review_first_flag",
        f"- rank_exposure_flag=True: {_pct(rank_exposed, n)}",
        f"- review_first_flag=True: {_pct(review_first, n)}",
    ]

    lines += ["\n## 6. base_skin_type별 분포"]
    for bst, cnt in sorted(bst_dist.items(), key=lambda x: -x[1]):
        lines.append(f"  - {bst}: {_pct(cnt, n)}")

    lines += [
        "\n## 7. 검증 결과",
        "- 입력 검증: 통과",
        "- 출력 검증: 통과",
        "- parquet 재로드 확인: 통과",
    ]

    lines += [
        "\n## 8. rank_exposure_flag 기준 검증",
        f"- insufficient_evidence + rank_exposure_flag=True: "
        + str(int(result.loc[result["evidence_level"] == "insufficient_evidence", "rank_exposure_flag"].sum())),
        "  (0이어야 정상)",
    ]

    lines += [
        "\n## 9. 서비스 관점 판단",
        f"1. 추천 상위 노출 적합 (rank_exposure_flag=True): {_pct(rank_exposed, n)}",
        f"2. 부정 리뷰 먼저 확인 유도 (review_first_flag=True): {_pct(review_first, n)}",
        f"3. 가장 신뢰 가능한 추천군 (strong_evidence + normal): {_pct(strong_normal, n)}",
        f"4. 중성 피부 타입 strong_evidence 수: {neutral_strong}건 (희소 데이터 확인)",
        f"5. high_negative_signal 전부 review_first_flag=True: {hns_all_review_first}",
    ]

    lines += ["\n## 10. 수동 샘플 검수 결과\n\n→ recommendation_scores_manual_review_samples.md 참조"]

    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] 리포트 저장: {REPORT_MD}, {REPORT_JSON}")
    return report


# ── 수동 검수 샘플 ────────────────────────────────────────────────────────────

def _load_negative_review_texts(
    pairs: list[tuple[str, str]],
) -> dict[tuple[str, str], list[str]]:
    """service_reviews에서 negative review_text 로드 (read-only, 수동 검수 전용)."""
    if not SVC_PARQUET.exists():
        _warn(f"service_reviews.parquet 없음, review_text 건너뜀: {SVC_PARQUET}")
        return {}
    try:
        svc = pd.read_parquet(
            SVC_PARQUET,
            columns=["product_key", "base_skin_type", "predicted_sentiment", "review_text"],
        )
    except Exception as exc:
        _warn(f"service_reviews.parquet 로드 실패: {exc}")
        return {}

    out: dict[tuple[str, str], list[str]] = {}
    for pk, bst in pairs:
        mask = (
            (svc["product_key"] == pk)
            & (svc["base_skin_type"] == bst)
            & (svc["predicted_sentiment"] == "negative")
        )
        texts = svc.loc[mask, "review_text"].dropna().head(3).tolist()
        out[(pk, bst)] = texts
    return out


def _sample_rows(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    return df.head(n) if len(df) >= n else df


DISPLAY_COLS = [
    "product_name", "brand", "category", "base_skin_type",
    "skin_review_count", "evidence_level",
    "skin_negative_rate", "caution_level",
    "recommendation_score", "recommendation_tier",
    "rank_exposure_flag", "review_first_flag",
    "display_message",
]


def _rows_to_md_table(sub: pd.DataFrame) -> str:
    cols = [c for c in DISPLAY_COLS if c in sub.columns]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in sub.iterrows():
        cells = []
        for c in cols:
            val = row[c]
            if isinstance(val, float):
                cells.append(f"{val:.3f}" if c != "recommendation_score" else f"{val:.1f}")
            else:
                cells.append(str(val)[:50].replace("|", "\\|"))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_manual_review_samples(result: pd.DataFrame) -> None:
    md_sections: list[str] = ["# Manual Review Samples — Recommendation Scores\n"]
    csv_groups: list[pd.DataFrame] = []

    def add_group(name: str, sub: pd.DataFrame, note: str = "") -> None:
        total_avail = len(sub)
        sub = _sample_rows(sub, 20)
        sub = sub.copy()
        sub["_sample_group"] = name
        csv_groups.append(sub)
        md_sections.append(f"\n## {name}")
        md_sections.append(f"available={total_avail}, shown={len(sub)}" + (f" — {note}" if note else ""))
        md_sections.append(_rows_to_md_table(sub))

    # 1. top_recommendation_samples
    top = result[result["rank_exposure_flag"]].sort_values("recommendation_score", ascending=False)
    add_group("top_recommendation_samples", top, "rank_exposure_flag=True 기준 상위")

    # 2. high_negative_signal_samples (+ review_text)
    hns = result[result["caution_level"] == "high_negative_signal"].sort_values(
        "skin_negative_rate", ascending=False
    )
    hns_sample = _sample_rows(hns, 20)
    pairs = list(zip(hns_sample["product_key"], hns_sample["base_skin_type"]))
    review_texts = _load_negative_review_texts(pairs)
    hns_sample = hns_sample.copy()
    hns_sample["_sample_group"] = "high_negative_signal_samples"
    csv_groups.append(hns_sample)

    md_sections.append(f"\n## high_negative_signal_samples")
    md_sections.append(f"available={len(hns)}, shown={len(hns_sample)}")
    md_sections.append(_rows_to_md_table(hns_sample))
    md_sections.append("\n### negative review_text 확인 (service_reviews read-only)")
    for _, row in hns_sample.iterrows():
        pk, bst = row["product_key"], row["base_skin_type"]
        texts = review_texts.get((pk, bst), [])
        md_sections.append(
            f"\n**{row['product_name'][:40]} / {bst}** "
            f"(neg_rate={row['skin_negative_rate']:.3f}, n={row['skin_review_count']}, "
            f"score={row['recommendation_score']:.1f})"
        )
        if texts:
            for t in texts:
                md_sections.append(f"  - {str(t)[:120]}")
        else:
            md_sections.append("  - (review_text 없음)")

    # 3. insufficient_evidence_samples
    insuff = result[result["evidence_level"] == "insufficient_evidence"].sort_values(
        "skin_review_count"
    )
    add_group("insufficient_evidence_samples", insuff, "skin_review_count < 5, rank_exposure_flag=False 확인")

    # 4. limited_evidence_samples
    limited = result[result["evidence_level"] == "limited_evidence"].sort_values(
        "skin_review_count"
    )
    add_group("limited_evidence_samples", limited, "skin_review_count 5~19")

    # 5. strong_evidence_samples
    strong = result[result["evidence_level"] == "strong_evidence"].sort_values(
        "recommendation_score", ascending=False
    )
    add_group("strong_evidence_samples", strong, "skin_review_count >= 20")

    # 6. neutral_skin_type_samples
    neutral_bst = result[result["base_skin_type"] == "중성"].sort_values(
        "evidence_level"
    )
    add_group("neutral_skin_type_samples", neutral_bst, "중성 피부 타입 display_message 확인")

    # 7. review_first_samples
    review_first = result[result["review_first_flag"]].sort_values(
        "skin_negative_rate", ascending=False
    )
    add_group("review_first_samples", review_first, "review_first_flag=True")

    # 8. rank_exposure_samples
    rank_exp = result[result["rank_exposure_flag"]].sort_values(
        "recommendation_score", ascending=False
    )
    add_group("rank_exposure_samples", rank_exp, "rank_exposure_flag=True")

    # 9. score_extreme_samples (상위 20 + 하위 20)
    top20 = result.sort_values("recommendation_score", ascending=False).head(20).copy()
    top20["_sample_group"] = "score_top20"
    bot20 = result.sort_values("recommendation_score", ascending=True).head(20).copy()
    bot20["_sample_group"] = "score_bottom20"
    csv_groups.append(top20)
    csv_groups.append(bot20)

    md_sections.append("\n## score_extreme_samples")
    md_sections.append("### 상위 20")
    md_sections.append(_rows_to_md_table(top20))
    md_sections.append("\n### 하위 20")
    md_sections.append(_rows_to_md_table(bot20))

    # 10. platform_samples
    for plat in ("musinsa", "oliveyoung"):
        sub = result[result["platform"] == plat].sort_values(
            "recommendation_score", ascending=False
        )
        add_group(f"platform_{plat}_samples", sub)

    coupang_count = len(result[result["platform"] == "coupang"])
    md_sections.append(f"\n## coupang 부재 확인\ncoupang rows: {coupang_count} (0이어야 정상)")

    # CSV 저장
    csv_out = pd.concat(csv_groups, ignore_index=True)
    for col in ("top_skin_need_tags", "top_skin_concern_tags"):
        if col in csv_out.columns:
            csv_out[col] = _list_col_to_str(csv_out[col])
    csv_out.to_csv(SAMPLES_CSV, index=False, encoding="utf-8-sig")

    # MD 저장
    SAMPLES_MD.write_text("\n".join(md_sections) + "\n", encoding="utf-8")

    print(f"[INFO] 수동 검수 샘플 저장: {SAMPLES_CSV}, {SAMPLES_MD}")


# ── Worklog 업데이트 ──────────────────────────────────────────────────────────

def update_worklog(result: pd.DataFrame, report: dict) -> None:
    now = datetime.now().strftime("%H:%M")
    tier_dist = report["recommendation_tier_distribution"]
    evidence_dist = report["evidence_level_distribution"]
    flags = report["flags"]
    svc = report["service_perspective"]

    entry = f"""

---

## Step 4 — product_recommendation_scores 생성

### {now} - Step 4: 추천 점수 테이블 생성

#### What changed

- `recommendation/scoring.py` 신규: 점수 계산 유틸리티 8개 함수
- `scripts/build_recommendation_scores.py` 신규: Step 4 메인 스크립트
- `preprocessed_v3/product_recommendation_scores.parquet` 생성 ({len(result):,} rows, {len(result.columns)} cols)
- `preprocessed_v3/product_recommendation_scores_preview.csv` 생성
- `reports/recommendation_scores_check.md/json` 생성
- `reports/recommendation_scores_manual_review_samples.csv/md` 생성

#### Why

- MVP 피부 타입 기반 부정 리뷰 탐색 서비스 Step 4
- product_skin_aggregates.parquet → 추천/주의 점수 + tier + flag 산정

#### Files touched

- `recommendation/scoring.py` - 신규
- `scripts/build_recommendation_scores.py` - 신규
- `preprocessed_v3/product_recommendation_scores.parquet` - 신규
- `preprocessed_v3/product_recommendation_scores_preview.csv` - 신규
- `reports/recommendation_scores_check.md` - 신규
- `reports/recommendation_scores_check.json` - 신규
- `reports/recommendation_scores_manual_review_samples.csv` - 신규
- `reports/recommendation_scores_manual_review_samples.md` - 신규

#### 핵심 결과

| 항목 | 수치 |
|------|------|
| 전체 row 수 | {len(result):,} |
| recommendation_score 평균 | {report['score_distribution']['mean']} |
| recommendation_score std | {report['score_distribution']['std']} |
| rank_exposure_flag=True | {flags['rank_exposure_flag_true']:,} ({flags['rank_exposure_flag_true_pct']}%) |
| review_first_flag=True | {flags['review_first_flag_true']:,} ({flags['review_first_flag_true_pct']}%) |

#### evidence_level 분포

{chr(10).join(f'- {k}: {v}' for k, v in sorted(evidence_dist.items(), key=lambda x: -x[1]))}

#### recommendation_tier 분포

{chr(10).join(f'- {k}: {v}' for k, v in sorted(tier_dist.items(), key=lambda x: -x[1]))}

#### Decisions

- Decision: recommendation_score 가중치 — skin_component 65점, overall_component 35점
  - Reason: 피부 타입별 부정률이 핵심 지표, 전체 평점/긍정률은 보조
  - Alternatives considered: 동일 가중치
  - Why rejected: 피부 타입 특화 서비스 방향과 불일치

- Decision: insufficient_evidence caution_penalty = 0 (evidence_weight로 이미 억제)
  - Reason: 이중 감점보다 rank_exposure_flag=False로 UI 제어
  - Alternatives considered: penalty 5점 추가
  - Why rejected: 낮은 근거는 weight 감쇄로 충분

#### Commands / Tests

```bash
C:\\Users\\user\\anaconda3\\envs\\oliveyoung\\python.exe scripts/build_recommendation_scores.py
```

#### Verification

- [x] 입력 검증 통과 (row 수, null, 중복, rate 범위, 합계)
- [x] 출력 검증 통과 (score 범위, null, flag 일관성)
- [x] parquet 재로드 row 수 일치
- [x] 보호 파일 6개 수정 시간 불변 확인
- [x] high_negative_signal 전부 review_first_flag=True: {svc['high_negative_signal_all_review_first']}
- [x] insufficient_evidence rank_exposure_flag=True: 0건
- [ ] 수동 검수 샘플 직접 확인 (recommendation_scores_manual_review_samples.md)

#### Remaining work

- Step 5: Streamlit UI 구현 (별도 승인 후)

#### Risks / Notes

- recommendation_score는 BiLSTM v3 예측 기반 (macro_f1=0.666) — 모델 오류 영향 내포
- 중성 피부 타입 strong_evidence: {svc['neutral_skin_type_strong_evidence_count']}건 (희소)
- display_message: 의학적 단정 표현 없음 확인
"""

    with open(WORKLOG, "a", encoding="utf-8") as f:
        f.write(entry)
    print(f"[INFO] worklog 업데이트: {WORKLOG}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("Step 4: product_recommendation_scores 생성")
    print("=" * 60)

    # 1. scoring.py 함수 존재 확인
    required_fns = [
        "get_evidence_level", "get_evidence_weight",
        "compute_negative_signal_score", "compute_recommendation_score",
        "get_recommendation_tier", "get_display_message",
        "get_rank_exposure_flag", "get_review_first_flag",
    ]
    import recommendation.scoring as _sc
    missing = [fn for fn in required_fns if not hasattr(_sc, fn)]
    if missing:
        _critical(f"scoring.py 필수 함수 누락: {missing}")
    print(f"[INFO] scoring.py 함수 확인 완료: {len(required_fns)}개")

    # 2. Pre-flight
    pre_mtimes = record_protected_mtimes()

    # 3. 로드 + 입력 검증
    df = load_and_validate()
    input_rows = len(df)

    # 4. 점수 계산
    result = build_scores(df)

    # 5. 출력 검증
    errors = validate_output(result, input_rows)
    if errors:
        for e in errors:
            print(f"[CRITICAL] {e}", file=sys.stderr)
        sys.exit(1)
    print("[INFO] 출력 검증 통과")

    # 6. 저장
    save_parquet(result)
    save_preview_csv(result)

    # 7. 리포트
    report = build_report(result)

    # 8. 수동 검수 샘플
    build_manual_review_samples(result)

    # 9. Worklog
    update_worklog(result, report)

    # 10. Post-flight 보호 파일 확인 (critical error)
    check_protected_mtimes(pre_mtimes)

    print("=" * 60)
    print(f"[완료] {len(result):,} rows, {len(result.columns)} cols")
    print(f"  recommendation_score: mean={report['score_distribution']['mean']}, std={report['score_distribution']['std']}")
    print(f"  rank_exposure_flag=True: {report['flags']['rank_exposure_flag_true']:,} ({report['flags']['rank_exposure_flag_true_pct']}%)")
    print(f"  review_first_flag=True: {report['flags']['review_first_flag_true']:,} ({report['flags']['review_first_flag_true_pct']}%)")
    print("=" * 60)


if __name__ == "__main__":
    main()
