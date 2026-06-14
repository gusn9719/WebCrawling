"""Data loading utilities for sentiment model training."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


LABEL_TO_ID = {
    "negative": 0,
    "neutral": 1,
    "positive": 2,
}
ID_TO_LABEL = {label_id: label for label, label_id in LABEL_TO_ID.items()}
CLASS_NAMES = [ID_TO_LABEL[index] for index in sorted(ID_TO_LABEL)]
ALLOWED_LABEL_IDS = set(ID_TO_LABEL)
TEXT_COLUMN_PRIORITY = ("tokens_str", "clean_review")


@dataclass(frozen=True)
class TextLabelDataset:
    texts: np.ndarray
    labels: np.ndarray
    text_column: str
    dropped_text_rows: int
    source_path: Path


def load_train_val(
    train_path: str | Path = "preprocessed/train.parquet",
    val_path: str | Path = "preprocessed/val.parquet",
) -> tuple[TextLabelDataset, TextLabelDataset]:
    """Load train/validation parquet files for sentiment training."""
    train = load_split(train_path)
    val = load_split(val_path)
    return train, val


def load_split(path: str | Path) -> TextLabelDataset:
    """Load one parquet split and return text inputs with validated labels."""
    split_path = Path(path)
    if not split_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {split_path}")

    frame = pd.read_parquet(split_path)
    text_column = select_text_column(frame, split_path)
    validate_labels(frame, split_path)

    text_values = frame[text_column]
    missing_mask = text_values.isna()
    non_missing_text = text_values[~missing_mask].astype(str).str.strip()
    empty_mask = non_missing_text.eq("")

    valid_index = non_missing_text.index[~empty_mask]
    dropped_rows = int(missing_mask.sum() + empty_mask.sum())

    filtered = frame.loc[valid_index]
    texts = non_missing_text.loc[valid_index].to_numpy(dtype=object)
    labels = filtered["sentiment_id"].astype(int).to_numpy()

    return TextLabelDataset(
        texts=texts,
        labels=labels,
        text_column=text_column,
        dropped_text_rows=dropped_rows,
        source_path=split_path,
    )


def select_text_column(frame: pd.DataFrame, path: Path) -> str:
    """Choose the text feature column without using rating-derived fields."""
    for column in TEXT_COLUMN_PRIORITY:
        if column in frame.columns:
            return column
    expected = ", ".join(TEXT_COLUMN_PRIORITY)
    raise ValueError(f"{path} must contain one of these text columns: {expected}")


def validate_labels(frame: pd.DataFrame, path: Path) -> None:
    """Validate that sentiment_id contains only the final 3-class labels."""
    if "sentiment_id" not in frame.columns:
        raise ValueError(f"{path} must contain sentiment_id")

    label_values = frame["sentiment_id"].dropna()
    if len(label_values) != len(frame):
        raise ValueError(f"{path} contains missing sentiment_id values")

    numeric_labels = pd.to_numeric(label_values, errors="raise")
    integer_mask = numeric_labels.eq(numeric_labels.astype(int))
    if not bool(integer_mask.all()):
        invalid_examples = numeric_labels[~integer_mask].head(10).tolist()
        raise ValueError(
            f"{path} contains non-integer sentiment_id values: {invalid_examples}"
        )

    unique_values = set(numeric_labels.astype(int).unique().tolist())
    invalid_values = sorted(unique_values - ALLOWED_LABEL_IDS)
    if invalid_values:
        raise ValueError(
            f"{path} contains invalid sentiment_id values: {invalid_values}. "
            "Allowed values are 0, 1, 2 only."
        )


def print_dataset_summary(train: TextLabelDataset, val: TextLabelDataset) -> None:
    """Print the text handling policy and split sizes."""
    print("Text feature policy: use tokens_str first, otherwise clean_review.")
    print("Rating/score/star columns are not used as model features.")
    for name, split in (("train", train), ("validation", val)):
        print(
            f"{name}: rows={len(split.labels)}, text_column={split.text_column}, "
            f"dropped_missing_or_empty_text_rows={split.dropped_text_rows}"
        )
