"""
상품별/피부타입별 집계 유틸리티.

pandas / collections 외 의존성 없음.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

# ── 신뢰도 레이블 ─────────────────────────────────────────────────────────────
_CONFIDENCE_THRESHOLDS = ((0, "근거 부족"), (5, "참고 가능"), (20, "비교적 신뢰 가능"))

# ── 주의 레벨 메시지 ──────────────────────────────────────────────────────────
CAUTION_MESSAGES: dict[str, str] = {
    "insufficient_evidence":
        "선택 피부 타입 리뷰 수가 적어 참고용으로만 확인하세요.",
    "high_negative_signal":
        "선택 피부 타입 리뷰에서 부정 반응 비율이 상대적으로 높습니다. "
        "구매 전 부정 리뷰를 먼저 확인하세요.",
    "moderate_negative_signal":
        "선택 피부 타입 리뷰에서 일부 부정 반응이 확인됩니다.",
    "normal":
        "선택 피부 타입 리뷰 기준으로 특별히 높은 부정 신호는 확인되지 않습니다.",
}


# ── 공개 API ─────────────────────────────────────────────────────────────────

def get_confidence_label(review_count: int) -> str:
    """리뷰 수 기준 신뢰도 레이블 반환."""
    if review_count < 5:
        return "근거 부족"
    if review_count < 20:
        return "참고 가능"
    return "비교적 신뢰 가능"


def safe_rate(count: int | float, total: int | float) -> float:
    """0 나눗셈 안전 비율 계산. total이 0이면 0.0 반환."""
    if total == 0:
        return 0.0
    return float(count) / float(total)


def get_caution_level(skin_review_count: int, skin_negative_rate: float) -> str:
    """피부 타입별 리뷰 수/부정률 기준 주의 레벨 반환."""
    if skin_review_count < 5:
        return "insufficient_evidence"
    if skin_negative_rate >= 0.25:
        return "high_negative_signal"
    if skin_negative_rate >= 0.15:
        return "moderate_negative_signal"
    return "normal"


def get_caution_message(caution_level: str) -> str:
    """주의 레벨 → 사용자용 메시지 반환."""
    return CAUTION_MESSAGES.get(caution_level, "")


def arr_to_list(arr: Any) -> list:
    """parquet 재로드 후 numpy array → Python list 변환 (비어 있으면 [])."""
    if arr is None:
        return []
    try:
        if len(arr) == 0:
            return []
        return list(arr)
    except TypeError:
        return []


def collect_top_tags(series, n: int = 5) -> list[str]:
    """pandas Series of list-like → top N 태그 반환."""
    c: Counter = Counter()
    for item in series:
        tags = arr_to_list(item)
        if tags:
            c.update(tags)
    return [t for t, _ in c.most_common(n)]
