"""
외부(무신사·쿠팡) CSV를 올리브영 ReviewSchema 호환 JSONL로 변환.

출력: oliveyoung_crawler/output_external/
  musinsa_reviews.jsonl
  coupang_reviews.jsonl

실행:
    C:\\Users\\user\\anaconda3\\envs\\oliveyoung\\python.exe normalize_external.py
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# ── 경로 ──────────────────────────────────────────────────────────────────────
_SCRIPT_DIR  = Path(__file__).resolve().parent   # oliveyoung_crawler/
_DATA_ROOT   = _SCRIPT_DIR.parent               # D:\_WebCrawling\
MUSINSA_CSV  = _DATA_ROOT / "musinsa_beauty_TOTAL.csv"
COUPANG_DIR  = _DATA_ROOT / "쿠팡"
OUTPUT_DIR   = _SCRIPT_DIR / "output_external"


# ── 유틸 ──────────────────────────────────────────────────────────────────────
def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:8]


def _excel_serial_to_date(serial) -> str:
    """Excel 날짜 일련번호(int/float) → 'YYYY-MM-DD'."""
    try:
        n = int(serial)
        d = datetime(1899, 12, 30) + timedelta(days=n)
        return d.strftime("%Y-%m-%d")
    except Exception:
        return ""


def _musinsa_date(raw: str) -> str:
    """'26.05.04' → '2026-05-04'. 두 자리 연도는 '20XX' 로 보정."""
    try:
        parts = str(raw).strip().split(".")
        if len(parts) == 3:
            yy, mm, dd = parts
            year = f"20{yy}" if len(yy) == 2 else yy
            return f"{year}-{mm}-{dd}"
    except Exception:
        pass
    return ""


def _write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  저장: {path.name}  ({len(records):,}건)")


def _to_int(val, default=None):
    try:
        v = int(val)
        return v
    except (ValueError, TypeError):
        return default


def _to_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ── 무신사 ────────────────────────────────────────────────────────────────────
def normalize_musinsa() -> None:
    print("=== 무신사 ===")
    if not MUSINSA_CSV.exists():
        print(f"  파일 없음: {MUSINSA_CSV}")
        return

    df = pd.read_csv(MUSINSA_CSV, encoding="utf-8-sig", low_memory=False)
    print(f"  원본 행 수: {len(df):,}")

    records: list[dict] = []
    seen: set[str] = set()

    for _, row in df.iterrows():
        pid   = str(row.get("product_id") or "").strip()
        rtext = str(row.get("review_text") or "").strip()
        if not pid or not rtext:
            continue

        rid = f"musinsa_{pid}_{_short_hash(rtext)}"
        if rid in seen:
            continue
        seen.add(rid)

        skin_type = str(row.get("skin_type") or "").strip() or None

        records.append({
            "platform":      "musinsa",
            "product_id":    pid,
            "review_id":     rid,
            "product_name":  str(row.get("product_name") or "").strip(),
            "brand":         str(row.get("brand_name") or "").strip() or None,
            "category":      "beauty",
            "price":         _to_int(row.get("price")),
            "rating":        _to_float(row.get("rating")),
            "review_text":   rtext,
            "review_date":   _musinsa_date(row.get("date", "")),
            "skin_type":     skin_type,
            "skin_concern":  None,
            "reviewer_age":  None,
            "helpful_count": _to_int(row.get("helpful"), 0),
            "photo_exists":  False,
            "crawled_at":    str(row.get("crawled_at") or "").strip(),
            "raw_url":       str(row.get("product_url") or "").strip() or None,
        })

    print(f"  중복 제거 후: {len(records):,}건")
    _write_jsonl(records, OUTPUT_DIR / "musinsa_reviews.jsonl")


# ── 쿠팡 ──────────────────────────────────────────────────────────────────────
def normalize_coupang() -> None:
    print("\n=== 쿠팡 ===")
    if not COUPANG_DIR.exists():
        print(f"  디렉토리 없음: {COUPANG_DIR}")
        return

    csv_files = sorted(COUPANG_DIR.glob("coupang_reviews*.csv"))
    if not csv_files:
        print(f"  CSV 없음: {COUPANG_DIR}")
        return

    dfs: list[pd.DataFrame] = []
    for p in csv_files:
        try:
            tmp = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
            dfs.append(tmp)
            print(f"  {p.name}: {len(tmp):,}건")
        except Exception as e:
            print(f"  {p.name} 로드 실패: {e}")

    if not dfs:
        return

    combined = pd.concat(dfs, ignore_index=True)
    print(f"  합산 총계: {len(combined):,}건")

    combined = combined.drop_duplicates(subset=["review_id"])
    print(f"  review_id 중복 제거 후: {len(combined):,}건")

    records: list[dict] = []
    for _, row in combined.iterrows():
        rid_raw = row.get("review_id")
        pid_raw = row.get("product_id")
        rtext   = str(row.get("review_content") or "").strip()
        if not rtext or pd.isna(rid_raw):
            continue

        rid = f"coupang_{int(rid_raw)}"
        pid = f"coupang_{int(pid_raw)}" if not pd.isna(pid_raw) else "coupang_unknown"

        review_date_raw = row.get("review_date")
        review_date = (
            _excel_serial_to_date(review_date_raw)
            if pd.notna(review_date_raw)
            else ""
        )

        records.append({
            "platform":      "coupang",
            "product_id":    pid,
            "review_id":     rid,
            "product_name":  str(row.get("product_name") or "").strip(),
            "brand":         None,
            "category":      "beauty",
            "price":         None,
            "rating":        _to_float(row.get("rating")),
            "review_text":   rtext,
            "review_date":   review_date,
            "skin_type":     None,
            "skin_concern":  None,
            "reviewer_age":  None,
            "helpful_count": 0,
            "photo_exists":  False,
            "crawled_at":    "",
            "raw_url":       None,
        })

    print(f"  최종 레코드: {len(records):,}건")
    _write_jsonl(records, OUTPUT_DIR / "coupang_reviews.jsonl")


def main() -> None:
    normalize_musinsa()
    normalize_coupang()
    print(f"\n완료. 출력 디렉토리: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
