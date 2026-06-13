"""학습/검증 데이터 분리.

수업 흐름에 맞춰 확정 학습 데이터만 train/validation = 8:2 로 나눈다.
별점과 본문 감성 단서가 강하게 충돌한 ambiguous 데이터는 이 단계에 넣지 않는다.
"""

from __future__ import annotations

import pandas as pd
from sklearn.model_selection import train_test_split

from . import config


def _dist(df: pd.DataFrame) -> dict[str, int]:
    counts = df["sentiment_label"].value_counts().to_dict()
    return {label: int(counts.get(label, 0)) for label in ["negative", "neutral", "positive"]}


def train_val(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """확정 데이터만 8:2 로 나누고 sentiment_id 기준 stratify 를 적용한다."""
    assert abs(config.TRAIN_RATIO + config.VAL_RATIO - 1.0) < 1e-9

    train, val = train_test_split(
        df,
        test_size=config.VAL_RATIO,
        stratify=df["sentiment_id"],
        random_state=config.RANDOM_SEED,
    )

    train = train.reset_index(drop=True)
    val = val.reset_index(drop=True)

    print("[split] train/validation 크기와 라벨 분포:")
    print(f"  train      {len(train):>7,}  {_dist(train)}")
    print(f"  validation {len(val):>7,}  {_dist(val)}")

    return {"train": train, "val": val}
