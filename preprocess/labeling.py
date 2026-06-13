"""별점 후보 라벨과 본문 감성 단서를 함께 보는 라벨링.

별점은 사람이 직접 붙인 정답이라기보다 약한 후보 라벨로 사용한다.
화장품 리뷰에서는 높은 별점에도 "따갑다", "트러블이 났다" 같은 불만이
본문에 길게 들어가는 경우가 있어, 간단한 규칙 기반 텍스트 단서와 비교한다.

text_rule_label 은 사람이 검수한 정답 라벨이 아니다. 본문에 드러난 감성 표현을
작게 확인하는 단서이며, 별점과 명백히 충돌하는 리뷰를 ambiguous 로 분리해
라벨 노이즈를 줄이기 위한 1차 장치다.
"""

from __future__ import annotations

import re

import pandas as pd

from . import config


LABEL_ORDER = ["negative", "neutral", "positive"]


def _rating_label(rating: float) -> str | None:
    """별점을 1차 후보 라벨로 변환한다."""
    if rating in config.NEG_RATINGS:
        return "negative"
    if rating in config.NEUTRAL_RATINGS:
        return "neutral"
    if rating in config.POS_RATINGS:
        return "positive"
    return None


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _mask_keywords(text: str, keywords: list[str]) -> str:
    masked = text
    for keyword in keywords:
        masked = masked.replace(keyword, " ")
    return masked


def _contains_any_pattern(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _mask_patterns(text: str, patterns: list[str]) -> str:
    masked = text
    for pattern in patterns:
        masked = re.sub(pattern, " ", masked)
    return masked


def _text_rule_label(text: str) -> str:
    """간단한 도메인 키워드로 본문 감성 단서를 찾는다.

    이 값은 사람이 직접 붙인 정답이 아니라 규칙 기반 힌트다.
    """
    absence_positive = _contains_any(
        text, config.NEGATIVE_ABSENCE_KEYWORDS
    ) or _contains_any_pattern(text, config.NEGATIVE_ABSENCE_PATTERNS)
    negative_scan_text = _mask_keywords(
        text,
        config.NEGATIVE_ABSENCE_KEYWORDS + config.NEGATIVE_CONTEXT_EXCEPTIONS,
    )
    negative_scan_text = _mask_patterns(
        negative_scan_text,
        config.NEGATIVE_ABSENCE_PATTERNS,
    )

    positive = absence_positive or _contains_any(text, config.POSITIVE_KEYWORDS)
    negative = _contains_any(negative_scan_text, config.NEGATIVE_KEYWORDS)

    if positive and negative:
        return "mixed"
    if positive:
        return "positive"
    if negative:
        return "negative"
    return "unknown"


def _finalize_label(row: pd.Series) -> dict[str, object]:
    rating_label = row["rating_label"]
    text_label = row["text_rule_label"]

    result = {
        "sentiment_label": rating_label,
        "sentiment_id": config.LABEL_TO_ID.get(rating_label),
        "label_confidence": "medium",
        "label_source": "rating_based",
        "is_ambiguous": False,
        "ambiguous_reason": None,
    }

    if text_label == "unknown":
        return result

    if text_label == "mixed":
        result.update(
            {
                "is_ambiguous": True,
                "label_confidence": "low",
                "label_source": "ambiguous_conflict",
                "ambiguous_reason": "mixed_text",
            }
        )
        return result

    if rating_label == text_label:
        result.update(
            {
                "sentiment_label": rating_label,
                "sentiment_id": config.LABEL_TO_ID[rating_label],
                "label_confidence": "high",
                "label_source": "rating_text_agree",
            }
        )
        return result

    if rating_label == "positive" and text_label == "negative":
        result.update(
            {
                "is_ambiguous": True,
                "label_confidence": "low",
                "label_source": "ambiguous_conflict",
                "ambiguous_reason": "high_rating_but_negative_text",
            }
        )
        return result

    if rating_label == "negative" and text_label == "positive":
        result.update(
            {
                "is_ambiguous": True,
                "label_confidence": "low",
                "label_source": "ambiguous_conflict",
                "ambiguous_reason": "low_rating_but_positive_text",
            }
        )
        return result

    # 3점(neutral)에 명확한 긍정/부정 단서가 있으면 본문 단서로 보정한다.
    if rating_label == "neutral" and text_label in {"negative", "positive"}:
        result.update(
            {
                "sentiment_label": text_label,
                "sentiment_id": config.LABEL_TO_ID[text_label],
                "label_confidence": "medium",
                "label_source": "text_corrected",
            }
        )

    return result


def _print_dist(title: str, series: pd.Series) -> None:
    print(title)
    counts = series.value_counts(dropna=False)
    for label in LABEL_ORDER + ["mixed", "unknown"]:
        if label in counts:
            print(f"  {label:<8} {counts[label]:>7,}")
    extra = [idx for idx in counts.index if idx not in LABEL_ORDER + ["mixed", "unknown"]]
    for label in extra:
        print(f"  {str(label):<8} {counts[label]:>7,}")


def label_by_rating_and_text(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """라벨 컬럼을 추가하고 확정 데이터와 ambiguous 데이터를 나눠 반환한다."""
    df = df.copy()

    df["rating_label"] = df["rating"].apply(_rating_label)
    before = len(df)
    df = df.dropna(subset=["rating_label"]).copy()
    dropped = before - len(df)
    if dropped:
        print(f"[label] 지원하지 않는 별점 제거: {before:,} → {len(df):,} (-{dropped:,})")

    df["text_rule_label"] = df["clean_review"].apply(_text_rule_label)

    decisions = df.apply(_finalize_label, axis=1, result_type="expand")
    df = pd.concat([df, decisions], axis=1)
    df["sentiment_id"] = df["sentiment_id"].astype("Int64")

    _print_dist("[label] 별점 기준 라벨 분포:", df["rating_label"])
    _print_dist("[label] 텍스트 규칙 기준 라벨 분포:", df["text_rule_label"])

    ambiguous = df[df["is_ambiguous"]].reset_index(drop=True)
    confirmed = df[
        (~df["is_ambiguous"])
        & (df["sentiment_label"].isin(LABEL_ORDER))
        & (df["sentiment_id"].notna())
    ].reset_index(drop=True)
    confirmed["sentiment_id"] = confirmed["sentiment_id"].astype(int)

    print(f"[label] 최종 학습 사용 데이터 수: {len(confirmed):,}")
    print(f"[label] ambiguous 제외 데이터 수: {len(ambiguous):,}")
    ratio = len(ambiguous) / len(df) * 100 if len(df) else 0.0
    print(f"[label] ambiguous 비율: {ratio:.1f}%")
    _print_dist("[label] 최종 sentiment_label 분포:", confirmed["sentiment_label"])

    return confirmed, ambiguous


def conflict_examples(ambiguous: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """별점과 텍스트 단서가 충돌한 대표 예시를 반환한다."""
    reasons = {
        "high_rating_but_negative_text",
        "low_rating_but_positive_text",
    }
    examples = ambiguous[ambiguous["ambiguous_reason"].isin(reasons)].copy()
    columns = [
        "rating",
        "rating_label",
        "text_rule_label",
        "ambiguous_reason",
        "review_text",
    ]
    return examples[columns].head(n)
