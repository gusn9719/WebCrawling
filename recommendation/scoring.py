"""
추천/주의 점수 계산 유틸리티.

pandas / sys 의존성 없음. 순수 계산 함수 모음.
"""
from __future__ import annotations

# ── 상수 ─────────────────────────────────────────────────────────────────────

EVIDENCE_WEIGHTS: dict[str, float] = {
    "strong_evidence": 1.0,
    "limited_evidence": 0.7,
    "insufficient_evidence": 0.3,
}

CAUTION_PENALTY: dict[str, float] = {
    "high_negative_signal": 20.0,
    "moderate_negative_signal": 10.0,
    "insufficient_evidence": 0.0,
    "normal": 0.0,
}

# ── 공개 API ─────────────────────────────────────────────────────────────────


def get_evidence_level(skin_review_count: int) -> str:
    """리뷰 수 기준 근거 레벨 반환."""
    if skin_review_count >= 20:
        return "strong_evidence"
    if skin_review_count >= 5:
        return "limited_evidence"
    return "insufficient_evidence"


def get_evidence_weight(evidence_level: str) -> float:
    """근거 레벨 → 가중치 반환."""
    return EVIDENCE_WEIGHTS[evidence_level]


def compute_negative_signal_score(
    skin_negative_rate: float,
    evidence_weight: float,
) -> float:
    """부정 신호 점수 (0~1). skin_negative_rate × evidence_weight."""
    return round(skin_negative_rate * evidence_weight, 6)


def compute_recommendation_score(
    skin_negative_rate: float,
    evidence_weight: float,
    caution_level: str,
    avg_rating: float,
    overall_positive_rate: float,
    overall_negative_rate: float,
) -> float:
    """추천 점수 (0~100).

    - skin_component  (0~65): (1 - neg_rate) * evidence_weight * 65
    - overall_component (0~35): (rating/5)*20 + pos_rate*10 + (1-neg_rate)*5
    - caution_penalty: high_negative_signal=20, moderate=10, else=0
    """
    skin_component = (1.0 - skin_negative_rate) * evidence_weight * 65.0
    rating_component = (avg_rating / 5.0) * 20.0
    overall_pos_component = overall_positive_rate * 10.0
    overall_neg_component = (1.0 - overall_negative_rate) * 5.0
    overall_component = rating_component + overall_pos_component + overall_neg_component
    penalty = CAUTION_PENALTY.get(caution_level, 0.0)
    raw = skin_component + overall_component - penalty
    return round(max(0.0, min(100.0, raw)), 2)


def get_recommendation_tier(
    evidence_level: str,
    caution_level: str,
    recommendation_score: float,
) -> str:
    """추천 티어 반환.

    우선순위: insufficient_evidence → negative_review_first → caution_check → 점수 기반
    """
    if evidence_level == "insufficient_evidence":
        return "insufficient_evidence"
    if caution_level == "high_negative_signal":
        return "negative_review_first"
    if caution_level == "moderate_negative_signal":
        return "caution_check"
    if recommendation_score >= 70.0 and evidence_level == "strong_evidence":
        return "strong_candidate"
    if recommendation_score >= 50.0:
        return "review_before_buying"
    return "limited_evidence"


def get_display_message(
    caution_level: str,
    evidence_level: str,
    base_skin_type: str,
    skin_review_count: int,
) -> str:
    """사용자용 표시 메시지 반환.

    금지 표현: 안전하다 / 트러블이 나지 않는다 / 피부에 적합하다 / 위험 상품이다 / 피해야 한다
    """
    if caution_level == "high_negative_signal":
        base = (
            "선택 피부 타입 리뷰에서 부정 신호가 상대적으로 높습니다. "
            "구매 전 부정 리뷰를 먼저 확인하세요."
        )
    elif caution_level == "moderate_negative_signal":
        base = (
            "선택 피부 타입 리뷰에서 일부 부정 반응이 확인됩니다. "
            "부정 리뷰를 먼저 확인하세요."
        )
    elif evidence_level == "insufficient_evidence":
        base = "선택 피부 타입 리뷰 수가 적어 참고용으로만 확인하세요."
    elif evidence_level == "limited_evidence":
        base = "선택 피부 타입 리뷰 근거가 제한적입니다. 실제 구매 전 리뷰 본문을 확인하세요."
    else:
        base = "선택 피부 타입 리뷰 기준 부정 신호가 낮은 편입니다."

    if base_skin_type == "중성" and evidence_level in ("insufficient_evidence", "limited_evidence"):
        return base + " (중성 피부 타입은 전반적으로 리뷰 근거가 적습니다.)"
    return base


def get_rank_exposure_flag(evidence_level: str, caution_level: str) -> bool:
    """추천 상위 노출 허용 여부. strong_evidence이고 high_negative_signal이 아닌 경우만 True."""
    return evidence_level == "strong_evidence" and caution_level != "high_negative_signal"


def get_review_first_flag(caution_level: str, skin_negative_rate: float) -> bool:
    """리뷰 먼저 확인 유도 여부. high/moderate caution 또는 neg_rate >= 0.20이면 True."""
    return (
        caution_level in ("high_negative_signal", "moderate_negative_signal")
        or skin_negative_rate >= 0.20
    )
