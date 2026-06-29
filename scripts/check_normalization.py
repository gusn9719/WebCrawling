"""
정규화 품질 점검 스크립트.

원본 parquet 파일은 절대 수정하지 않는다.

생성 파일:
    reports/normalization_check.md
    reports/normalization_check.json
    reports/normalization_manual_review_samples.csv
    reports/normalization_manual_review_samples.md

Usage:
    C:\\Users\\user\\anaconda3\\envs\\oliveyoung\\python.exe scripts/check_normalization.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from recommendation.normalization import (
    _is_missing,
    normalize_skin_concern,
    normalize_skin_type,
)

_DATA_DIR    = _ROOT / "preprocessed_v3"
_REPORTS_DIR = _ROOT / "reports"

TRAIN_PATH = _DATA_DIR / "train.parquet"
VAL_PATH   = _DATA_DIR / "val.parquet"

# skin_need_tags / skin_concern_tags 에서 "알려진 태그" 집합
# 이 집합에 없는 태그가 남아 있으면 ambiguous_or_unmapped 로 분류
KNOWN_TAGS: frozenset[str] = frozenset({
    "진정", "보습", "모공", "트러블", "유수분 조절",
    "탄력", "영양공급", "미백", "홍조", "각질", "주름",
})


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _top_counter(series_of_lists: pd.Series, n: int = 30) -> list[tuple[str, int]]:
    counter: Counter = Counter()
    for lst in series_of_lists:
        if isinstance(lst, list):
            counter.update(lst)
    return counter.most_common(n)


def _df_to_md(df: pd.DataFrame) -> str:
    """tabulate 없이 DataFrame → markdown 테이블."""
    cols = df.columns.tolist()
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep    = "| " + " | ".join("---" for _ in cols) + " |"
    rows   = []
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            val = row[c]
            # list 는 짧게 표시
            if isinstance(val, list):
                val = str(val)
            cells.append(str(val).replace("|", "\\|").replace("\n", " "))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + rows)


# ── 1. 데이터 로드 ────────────────────────────────────────────────────────────

def _load_data() -> pd.DataFrame:
    print("[1/6] 데이터 로드 중...")
    train = pd.read_parquet(TRAIN_PATH)
    val   = pd.read_parquet(VAL_PATH)
    df    = pd.concat([train, val], ignore_index=True)
    print(f"      train {len(train):,}행 + val {len(val):,}행 = 합계 {len(df):,}행")
    return df


# ── 2. 정규화 적용 ────────────────────────────────────────────────────────────

def _apply_normalizations(df: pd.DataFrame) -> pd.DataFrame:
    print("[2/6] 정규화 적용 중...")
    df = df.copy()   # 원본 수정 금지

    st = df["skin_type"].apply(normalize_skin_type)
    sc = df["skin_concern"].apply(normalize_skin_concern)

    df["base_skin_type"]                    = st.apply(lambda d: d["base_skin_type"])
    df["skin_type_tags"]                    = st.apply(lambda d: d["skin_type_tags"])
    df["skin_need_tags"]                    = st.apply(lambda d: d["skin_need_tags"])
    df["skin_type_normalization_status"]    = st.apply(lambda d: d["skin_type_normalization_status"])
    df["skin_concern_tags"]                 = sc.apply(lambda d: d["skin_concern_tags"])
    df["skin_concern_codes"]                = sc.apply(lambda d: d["skin_concern_codes"])
    df["skin_concern_normalization_status"] = sc.apply(lambda d: d["skin_concern_normalization_status"])

    print("      완료")
    return df


# ── 3. 플랫폼별 커버리지 (_is_missing 기준) ───────────────────────────────────

def _platform_coverage(df: pd.DataFrame, col: str) -> dict:
    result = {}
    for plat in sorted(df["platform"].unique()):
        sub   = df[df["platform"] == plat]
        valid = int(sub[col].apply(lambda v: not _is_missing(v)).sum())
        result[plat] = {
            "valid_n": valid,
            "total":   int(len(sub)),
            "pct":     round(valid / len(sub) * 100, 1),
        }
    return result


# ── 4. 리포트 집계 ────────────────────────────────────────────────────────────

def _build_report(df: pd.DataFrame) -> dict:
    print("[3/6] 리포트 집계 중...")
    total = len(df)

    st_ok    = int((df["skin_type_normalization_status"] == "ok").sum())
    sc_valid = int(df["skin_concern_normalization_status"].isin(["ok", "code_only"]).sum())

    report = {
        "total_rows": total,
        "skin_type": {
            "valid_count":          st_ok,
            "valid_pct":            round(st_ok / total * 100, 1),
            "platform_coverage":    _platform_coverage(df, "skin_type"),
            "status_dist":          df["skin_type_normalization_status"].value_counts().to_dict(),
            "base_skin_type_dist":  df["base_skin_type"].value_counts(dropna=False).head(20).to_dict(),
            "top50_raw":            df["skin_type"].value_counts(dropna=False).head(50).to_dict(),
            "top30_need_tags":      _top_counter(df["skin_need_tags"], 30),
        },
        "skin_concern": {
            "valid_count":     sc_valid,
            "valid_pct":       round(sc_valid / total * 100, 1),
            "status_dist":     df["skin_concern_normalization_status"].value_counts().to_dict(),
            "top50_raw":       df["skin_concern"].value_counts(dropna=False).head(50).to_dict(),
            "top30_tags":      _top_counter(df["skin_concern_tags"], 30),
            "top30_codes":     _top_counter(df["skin_concern_codes"], 30),
        },
    }
    print("      완료")
    return report


# ── 5. 수동 검수 샘플 수집 ────────────────────────────────────────────────────

def _collect_samples(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    print("[4/6] 수동 검수 샘플 수집 중...")

    ST_COLS = [
        "platform", "product_id", "review_id", "skin_type",
        "base_skin_type", "skin_type_tags", "skin_need_tags",
        "skin_type_normalization_status",
    ]
    SC_COLS = [
        "platform", "product_id", "review_id", "skin_concern",
        "skin_concern_tags", "skin_concern_codes",
        "skin_concern_normalization_status",
    ]

    def _pick(mask: pd.Series, cols: list[str], n: int = 20) -> pd.DataFrame:
        sub = df[mask][cols]
        return sub.head(n).reset_index(drop=True)

    # 1. 빈도 상위 20개 원본값에서 각 1건
    top20_vals = df["skin_type"].value_counts(dropna=False).head(20).index.tolist()
    top_rows = []
    for v in top20_vals:
        m = (df["skin_type"] == v) if not (isinstance(v, float) and pd.isna(v)) else df["skin_type"].isna()
        hit = df[m]
        if len(hit) > 0:
            top_rows.append(hit.iloc[0])
    top_st = pd.DataFrame(top_rows)[ST_COLS].reset_index(drop=True) if top_rows else pd.DataFrame(columns=ST_COLS)

    samples = {
        "top_skin_type_samples": top_st,
        "random_skin_type_samples": _pick(
            df["skin_type_normalization_status"] == "ok", ST_COLS
        ).sample(min(20, (df["skin_type_normalization_status"] == "ok").sum()), random_state=42),
        "no_base_skin_type_samples": _pick(
            df["skin_type_normalization_status"] == "no_base_skin_type", ST_COLS
        ),
        "missing_skin_type_samples": _pick(
            df["skin_type_normalization_status"] == "missing", ST_COLS
        ),
        "skin_concern_code_mixed_samples": _pick(
            (df["skin_concern_normalization_status"] == "ok") &
            (df["skin_concern_codes"].apply(lambda c: isinstance(c, list) and len(c) > 0)),
            SC_COLS,
        ),
        "skin_concern_code_only_samples": _pick(
            df["skin_concern_normalization_status"] == "code_only", SC_COLS
        ),
        "ambiguous_or_unmapped_samples": _pick(
            df["skin_need_tags"].apply(
                lambda tags: isinstance(tags, list) and any(t not in KNOWN_TAGS for t in tags)
            ),
            ST_COLS,
        ),
    }

    for name, sdf in samples.items():
        print(f"      {name}: {len(sdf)}개")

    return samples


# ── 6. 출력 ───────────────────────────────────────────────────────────────────

def _write_json(report: dict, samples: dict) -> None:

    def _convert(obj):
        if isinstance(obj, dict):
            return {str(k): _convert(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_convert(i) for i in obj]
        return obj

    out = {
        "report":        _convert(report),
        "sample_counts": {k: len(v) for k, v in samples.items()},
    }
    path = _REPORTS_DIR / "normalization_check.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"      저장: {path.name}")


def _write_md(report: dict, samples: dict) -> None:
    lines: list[str] = []
    st = report["skin_type"]
    sc = report["skin_concern"]

    lines += [
        "# Normalization Check Report",
        "",
        "생성일: 2026-06-27",
        "",
        f"## 1. 전체 행 수",
        "",
        f"{report['total_rows']:,}건",
        "",
        "## 2. skin_type 유효 수",
        "",
        f"{st['valid_count']:,}건 ({st['valid_pct']}%)",
        "",
        "### 플랫폼별 커버리지 (_is_missing 기준)",
        "",
        "| 플랫폼 | 유효 수 | 전체 | 비율 |",
        "|---|---|---|---|",
    ]
    for plat, v in st["platform_coverage"].items():
        lines.append(f"| {plat} | {v['valid_n']:,} | {v['total']:,} | {v['pct']}% |")

    lines += [
        "",
        "## 3. skin_concern 유효 수",
        "",
        f"{sc['valid_count']:,}건 ({sc['valid_pct']}%)",
        "",
        "## 4. base_skin_type 분포",
        "",
        "| base_skin_type | 수 |",
        "|---|---|",
    ]
    for k, v in st["base_skin_type_dist"].items():
        lines.append(f"| {k} | {v:,} |")

    lines += [
        "",
        "## 5. skin_type_normalization_status 분포",
        "",
        "| status | 수 |",
        "|---|---|",
    ]
    for k, v in st["status_dist"].items():
        lines.append(f"| {k} | {v:,} |")

    lines += [
        "",
        "## 6. skin_concern_normalization_status 분포",
        "",
        "| status | 수 |",
        "|---|---|",
    ]
    for k, v in sc["status_dist"].items():
        lines.append(f"| {k} | {v:,} |")

    lines += ["", "## 7. Top 30 skin_need_tags", "", "| 태그 | 수 |", "|---|---|"]
    for tag, cnt in st["top30_need_tags"]:
        lines.append(f"| {tag} | {cnt:,} |")

    lines += ["", "## 8. Top 30 skin_concern_tags", "", "| 태그 | 수 |", "|---|---|"]
    for tag, cnt in sc["top30_tags"]:
        lines.append(f"| {tag} | {cnt:,} |")

    lines += ["", "## 9. Top 30 skin_concern_codes", "", "| 코드 | 수 |", "|---|---|"]
    for code, cnt in sc["top30_codes"]:
        lines.append(f"| {code} | {cnt:,} |")

    lines += ["", "## 10. Top 50 raw skin_type 값", "", "```"]
    for k, v in list(st["top50_raw"].items())[:50]:
        lines.append(f"{str(k):<60} {v:>8,}")
    lines += ["```", ""]

    lines += ["## 11. Top 50 raw skin_concern 값", "", "```"]
    for k, v in list(sc["top50_raw"].items())[:50]:
        lines.append(f"{str(k):<60} {v:>8,}")
    lines += ["```", ""]

    # 수동 검수 섹션
    lines += ["## 수동 샘플 검수 결과", "", "### 확인한 샘플 수", ""]
    for group, sdf in samples.items():
        lines.append(f"- {group}: {len(sdf)}개")

    lines += [
        "",
        "### 정상으로 판단한 예시",
        "",
        "| 원본 skin_type | base_skin_type | skin_need_tags | status |",
        "|---|---|---|---|",
    ]
    top_ok = samples.get("top_skin_type_samples", pd.DataFrame())
    for _, row in top_ok[top_ok["skin_type_normalization_status"] == "ok"].head(10).iterrows():
        lines.append(
            f"| {row['skin_type']} | {row['base_skin_type']} "
            f"| {row['skin_need_tags']} | {row['skin_type_normalization_status']} |"
        )

    lines += [
        "",
        "### 이상하거나 애매한 예시",
        "",
        "| 원본 skin_type | base_skin_type | skin_need_tags | 문제 |",
        "|---|---|---|---|",
    ]
    ambig = samples.get("ambiguous_or_unmapped_samples", pd.DataFrame())
    if ambig.empty:
        lines.append("| — | — | — | 없음 (모든 태그가 정상 매핑됨) |")
    else:
        for _, row in ambig.head(10).iterrows():
            lines.append(
                f"| {row['skin_type']} | {row['base_skin_type']} "
                f"| {row['skin_need_tags']} | 미매핑 태그 존재 |"
            )

    lines += [
        "",
        "### 수정한 규칙",
        "",
        "- (스크립트 자동 생성 — 추가 수정 사항은 여기에 기록)",
        "",
        "### 아직 남은 위험",
        "",
        "- C09/C10/C11/C12/C13 코드 의미 미확인",
        "- skin_concern 은 oliveyoung 플랫폼 전용 (musinsa/coupang 에 없음)",
        "",
        "### Step 2 진행 가능 여부",
        "",
        "- 가능/불가능: (수동 검수 후 판단)",
        "- 이유: ",
        "",
        "## 12. 다음 단계 service_reviews.parquet 권장 컬럼",
        "",
    ]
    suggested = [
        "review_id", "product_id", "product_name", "brand", "category",
        "rating", "sentiment_label", "clean_review",
        "skin_type", "base_skin_type", "skin_type_tags", "skin_need_tags",
        "skin_type_normalization_status",
        "skin_concern", "skin_concern_tags", "skin_concern_codes",
        "skin_concern_normalization_status",
        "platform", "review_date",
    ]
    for col in suggested:
        lines.append(f"- `{col}`")

    path = _REPORTS_DIR / "normalization_check.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"      저장: {path.name}")


def _write_samples(samples: dict) -> None:
    # CSV: 그룹 컬럼 추가 후 합치기
    parts = []
    for group, sdf in samples.items():
        if sdf.empty:
            continue
        tmp = sdf.copy()
        tmp.insert(0, "sample_group", group)
        # list 컬럼 → 문자열
        for col in tmp.columns:
            if tmp[col].apply(lambda x: isinstance(x, list)).any():
                tmp[col] = tmp[col].apply(lambda x: str(x) if isinstance(x, list) else x)
        parts.append(tmp)

    if parts:
        combined = pd.concat(parts, ignore_index=True)
        csv_path = _REPORTS_DIR / "normalization_manual_review_samples.csv"
        combined.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"      저장: {csv_path.name}")

    # MD: 그룹별 테이블
    md_lines = ["# 수동 검수 샘플", ""]
    for group, sdf in samples.items():
        count = len(sdf)
        md_lines.append(f"\n## {group} ({count}개)\n")
        if sdf.empty:
            md_lines.append("_(해당 샘플 없음)_")
            continue
        # list 컬럼 → 문자열 (표시용)
        display = sdf.copy()
        for col in display.columns:
            if display[col].apply(lambda x: isinstance(x, list)).any():
                display[col] = display[col].apply(lambda x: str(x) if isinstance(x, list) else x)
        md_lines.append(_df_to_md(display))

    md_path = _REPORTS_DIR / "normalization_manual_review_samples.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"      저장: {md_path.name}")


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    df      = _load_data()
    df      = _apply_normalizations(df)
    report  = _build_report(df)
    samples = _collect_samples(df)

    print("[5/6] 파일 저장 중...")
    _write_json(report, samples)
    _write_md(report, samples)
    _write_samples(samples)

    # 콘솔 핵심 수치 출력
    print("\n[6/6] 핵심 수치 요약")
    st = report["skin_type"]
    sc = report["skin_concern"]
    print(f"  전체 행 수         : {report['total_rows']:,}")
    print(f"  skin_type 유효     : {st['valid_count']:,} ({st['valid_pct']}%)")
    print(f"  skin_concern 유효  : {sc['valid_count']:,} ({sc['valid_pct']}%)")
    print(f"  base_skin_type 분포: {st['base_skin_type_dist']}")
    print(f"  skin_type status   : {st['status_dist']}")
    print(f"  skin_concern status: {sc['status_dist']}")
    print("\n완료!")


if __name__ == "__main__":
    main()
