"""텍스트 정제 단계.

수업(0526) 네이버 영화 리뷰 전처리의 핵심 4단계를 그대로 옮겨 적용:
    1) 결측치 제거
    2) 정제: 한글+공백만 남기기 → 빈 문자열은 결측치로 → 다시 결측치 제거
    3) 중복 제거 ('가나다라마바사' 같은 복붙 리뷰가 실제로 많다)
    4) 길이 필터  ← 수업에는 없는 단계. 너무 짧은 리뷰는 학습 신호가 없어 추가.

각 단계마다 before/after 행 수를 출력해서 파이프라인 어디서 얼마나 빠지는지
육안으로 확인할 수 있게 한다.
"""

from __future__ import annotations

import re

import pandas as pd

from . import config


# 미리 컴파일 (큰 데이터에 apply 할 때 누적 차이가 큼)
_HANGUL_ONLY_RE = re.compile(config.HANGUL_ONLY_PATTERN)
_LEADING_SPACE_RE = re.compile(r"^ +")
_MULTI_SPACE_RE = re.compile(r" +")


def _clean_text(s: str) -> str:
    """수업 흐름의 정제 한 줄.

    예) "ㅠㅠ 진짜 별로예요!!! ㅋㅋㅋ" → "진짜 별로예요"
    한글과 공백 외 문자는 모두 공백으로 치환 → 다중 공백 압축 → 앞 공백 제거.
    한글이 하나도 없던 문장은 빈 문자열로 반환한다 (다음 단계가 결측치 처리).
    """
    s = _HANGUL_ONLY_RE.sub(" ", s)
    s = _MULTI_SPACE_RE.sub(" ", s)
    s = _LEADING_SPACE_RE.sub("", s).strip()
    return s


def _log(stage: str, before: int, after: int) -> None:
    drop = before - after
    pct = drop / before * 100 if before else 0.0
    print(f"[clean] {stage:<20} {before:>7,} → {after:>7,}  (-{drop:,}, {pct:.1f}%)")


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """결측·정제·중복·길이 필터를 순서대로 적용.

    원본을 건드리지 않도록 copy 한 뒤 step 별로 변형.
    필요한 컬럼은 review_text, rating 두 개 — 나머지는 그대로 끌고 간다.
    """
    df = df.copy()

    # ── 1) review_text / rating 결측치 제거 ───────────────────────
    # rating 까지 결측이면 라벨 부여 자체가 불가하므로 같은 단계에서 처리.
    before = len(df)
    df = df.dropna(subset=["review_text", "rating"])
    df = df[df["review_text"].str.strip() != ""]
    _log("결측치 제거", before, len(df))

    # ── 2) 정제: 한글+공백만 ───────────────────────────────────────
    before = len(df)
    df["clean_review"] = df["review_text"].apply(_clean_text)
    # 정제 결과 빈 문자열은 한글이 전혀 없던 리뷰. 학습에 못 쓰니 제거.
    df = df[df["clean_review"] != ""]
    _log("한글 정제", before, len(df))

    # ── 3) 중복 제거 ───────────────────────────────────────────────
    # 동일 텍스트 복붙(특히 광고/봇 리뷰)이 카테고리 경계를 넘어 다수 존재한다.
    # subset 을 clean_review 로 잡아서 띄어쓰기/문장부호 차이는 무시한다.
    before = len(df)
    df = df.drop_duplicates(subset=["clean_review"])
    _log("중복 제거", before, len(df))

    # ── 4) 길이 필터 ───────────────────────────────────────────────
    # "좋아요", "굿" 같은 너무 짧은 리뷰는 형태소 분석해도 1~2 토큰밖에 안 남아
    # RNN 학습에 노이즈가 된다. 글자 수 기준으로 1차 필터.
    before = len(df)
    df = df[df["clean_review"].str.len() >= config.MIN_CHAR_LEN]
    _log(f"길이≥{config.MIN_CHAR_LEN}자 필터", before, len(df))

    return df.reset_index(drop=True)
