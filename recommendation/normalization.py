"""
피부 타입·고민 필드 정규화 유틸리티.

skin_type, skin_concern 원본 값을 받아 구조화된 dict로 변환한다.
pandas / re / math / typing 외 의존성 없음.
"""
from __future__ import annotations

import math
import re
from typing import Any

# ── 구분자 (정규식, 공백 변형 허용) ──────────────────────────────────────────
_ST_SEP = re.compile(r"\s*·\s*")   # skin_type:    · 주변 공백 허용
_SC_SEP = re.compile(r"\s*,\s*")   # skin_concern: , 주변 공백 허용

# ── 기본 피부 타입 ─────────────────────────────────────────────────────────────
_BASE_SKIN_TYPES: frozenset[str] = frozenset({
    "지성", "건성", "민감성", "복합성", "중성",
})

# ── 태그 정규화 맵 (skin_type 니즈·skin_concern 태그 공용) ────────────────────
_TAG_NORMALIZE: dict[str, str] = {
    "여드름":    "트러블",
    "유수분조절": "유수분 조절",
}

# ── 코드 패턴 ─────────────────────────────────────────────────────────────────
_CODE_RE = re.compile(r"^C\d+$")   # C09, C10, C11, C12, C13 …


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────
def _is_missing(value: Any) -> bool:
    """결측값 판단: None / float NaN / pd.NA / 빈 문자열 / 문자열 'nan'."""
    if value is None:
        return True
    try:
        if math.isnan(value):
            return True
    except (TypeError, ValueError):
        # pd.NA 는 math.isnan() 에서 TypeError 발생 → missing 아님으로 통과
        pass
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return stripped == "" or stripped.lower() == "nan"


def _normalize_tag(token: str) -> str:
    """단일 토큰에 정규화 맵 적용 (미등록 토큰은 원본 반환)."""
    return _TAG_NORMALIZE.get(token.strip(), token.strip())


def _expand_slash(token: str) -> list[str]:
    """'진정/보습' → ['진정', '보습'],  '모공' → ['모공'].

    '/' 로 분리 후 각 부분에 정규화 맵을 적용한다.
    """
    return [_normalize_tag(p) for p in token.split("/") if p.strip()]


# ── 공개 API ─────────────────────────────────────────────────────────────────
def normalize_skin_type(value: object) -> dict:
    """skin_type 원본 값을 구조화된 dict 로 변환한다.

    Returns:
        {
          "base_skin_type":                  str | None,
          "skin_type_tags":                  list[str],
          "skin_need_tags":                  list[str],
          "skin_type_normalization_status":  "ok" | "no_base_skin_type" | "missing",
        }

    Notes:
        - 구분자는 re.split(r"\\s*·\\s*") 로 처리해 공백 변형을 허용한다.
        - 첫 토큰이 기본 피부 타입(지성/건성/민감성/복합성/중성)일 때만
          base_skin_type 으로 인정하며, 그 외에는 no_base_skin_type 으로 처리한다.
        - 여드름 → 트러블, 유수분조절 → 유수분 조절 로 정규화한다.
        - 진정/보습 → ['진정', '보습'] 으로 분리한다.
    """
    if _is_missing(value):
        return {
            "base_skin_type": None,
            "skin_type_tags": [],
            "skin_need_tags": [],
            "skin_type_normalization_status": "missing",
        }

    tokens = [t for t in _ST_SEP.split(str(value).strip()) if t.strip()]

    if not tokens:
        return {
            "base_skin_type": None,
            "skin_type_tags": [],
            "skin_need_tags": [],
            "skin_type_normalization_status": "missing",
        }

    first = tokens[0].strip()

    if first in _BASE_SKIN_TYPES:
        needs: list[str] = []
        for t in tokens[1:]:
            needs.extend(_expand_slash(t))
        return {
            "base_skin_type": first,
            "skin_type_tags": [first],
            "skin_need_tags": needs,
            "skin_type_normalization_status": "ok",
        }
    else:
        # 첫 토큰이 기본 피부 타입이 아닌 경우 — 전 토큰을 니즈로 처리
        needs = []
        for t in tokens:
            needs.extend(_expand_slash(t))
        return {
            "base_skin_type": None,
            "skin_type_tags": [],
            "skin_need_tags": needs,
            "skin_type_normalization_status": "no_base_skin_type",
        }


def normalize_skin_concern(value: object) -> dict:
    """skin_concern 원본 값을 구조화된 dict 로 변환한다.

    Returns:
        {
          "skin_concern_tags":                  list[str],
          "skin_concern_codes":                 list[str],
          "skin_concern_normalization_status":  "ok" | "code_only" | "missing",
        }

    Notes:
        - 구분자는 re.split(r"\\s*,\\s*") 로 처리해 공백 변형을 허용한다.
        - C09, C10 등 코드성 값은 skin_concern_codes 에 보존한다 (의미 추측 안 함).
        - 태그에도 '/' 분리와 정규화 맵을 적용한다.
          예: '진정/보습' → ['진정', '보습'], '여드름' → '트러블'
    """
    if _is_missing(value):
        return {
            "skin_concern_tags": [],
            "skin_concern_codes": [],
            "skin_concern_normalization_status": "missing",
        }

    tokens = [t for t in _SC_SEP.split(str(value).strip()) if t.strip()]

    if not tokens:
        return {
            "skin_concern_tags": [],
            "skin_concern_codes": [],
            "skin_concern_normalization_status": "missing",
        }

    tags:  list[str] = []
    codes: list[str] = []

    for token in tokens:
        token = token.strip()
        if _CODE_RE.match(token):
            codes.append(token)
        else:
            # '/' 분리 + 정규화 맵 적용
            tags.extend(_expand_slash(token))

    if tags:
        status = "ok"
    elif codes:
        status = "code_only"
    else:
        status = "missing"   # 방어 경로

    return {
        "skin_concern_tags": tags,
        "skin_concern_codes": codes,
        "skin_concern_normalization_status": status,
    }
