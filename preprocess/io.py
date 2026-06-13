"""JSONL 리뷰 파일을 DataFrame 으로 로딩한다.

크롤러가 카테고리당 한 파일씩 떨군 jsonl 을 모두 합쳐 한 DataFrame 으로 만든다.
JSONL 은 한 줄에 dict 하나가 들어있는 형식이라 메모리 효율이 좋다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import config


def _load_one(path: Path) -> pd.DataFrame:
    """JSONL 파일 하나를 DataFrame 으로.

    pd.read_json(lines=True) 도 가능하지만, 손상된 라인 한 줄이 전체를 망치는
    문제가 있어 한 줄씩 읽으며 json.loads 로 가는 게 안전하다.
    크롤링 중간에 429 로 끊긴 흔적이 라인 단위로 남기 때문에 더더욱.
    """
    records: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                # 손상된 줄은 건너뛰고 경고만. 보통 마지막 한 줄이 깨진 경우.
                print(f"[io] skip {path.name}:{line_no}  ({e})")
    return pd.DataFrame(records)


def load_reviews(
    categories: list[str] | None = None,
    input_dir: Path | None = None,
) -> pd.DataFrame:
    """전 카테고리의 리뷰 jsonl 을 한 DataFrame 으로.

    Args:
        categories: 로드할 카테고리. None 이면 config.CATEGORIES 전체.
        input_dir:  입력 디렉토리. None 이면 config.INPUT_DIR.

    Returns:
        DataFrame. 컬럼은 크롤러 스키마와 동일하되, 다운스트림에서 쓰지 않는
        raw_url/crawled_at 등도 그대로 둔다(필요해질 때마다 컬럼 prune 하면
        잔실수가 늘어남 — 한 번에 다 끌고 가는 게 낫다).
    """
    categories = categories or config.CATEGORIES
    input_dir = input_dir or config.INPUT_DIR

    dfs: list[pd.DataFrame] = []
    for cat in categories:
        path = input_dir / f"{cat}_reviews.jsonl"
        if not path.exists():
            print(f"[io] WARN: {path} 없음, 건너뜀")
            continue
        df = _load_one(path)
        # category 컬럼은 jsonl 안에도 있지만, 누락 행이 있을 수 있어 강제 주입
        df["category"] = cat
        dfs.append(df)
        print(f"[io] {cat:>10}: {len(df):>6} 건")

    if not dfs:
        raise FileNotFoundError(f"입력 jsonl 을 한 개도 못 읽었다: {input_dir}")

    merged = pd.concat(dfs, ignore_index=True)

    # 타입 정리:
    #   - rating: float (크롤러 단계에서 float 로 들어옴, 그대로 유지)
    #   - review_date: datetime (시계열 분석 가능하게)
    #   - review_text: str (혹시 null 이 섞여 있어도 다음 cleaning 단계에서 처리)
    merged["review_date"] = pd.to_datetime(merged["review_date"], errors="coerce")

    print(f"[io] TOTAL: {len(merged):,} 건")
    return merged
