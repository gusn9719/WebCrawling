"""형태소 분석 + 불용어 제거.

수업(0526) 흐름:
    Okt().morphs(text)  →  토큰 리스트
여기에 두 가지를 더 얹는다:
    - stem=True   "갔어요" → "가다" 어간 통일 (vocab 축소)
    - 불용어/1글자 토큰 제거 (RNN 노이즈 감소)

왜 다른 분석기 말고 Okt 인가
    - 수업에서 다뤄 익숙함
    - Windows 설치가 가장 무난 (Mecab 은 설치 까다로움)
    - 화장품 리뷰처럼 짧고 구어체 많은 텍스트에 무난한 성능

성능 메모: 20만 건 형태소 분석은 단일 프로세스로 약 10~30분.
tqdm 으로 진행률 표시하고, 한 번 계산한 결과는 parquet 으로 저장해서
실험 반복 시 재토큰화하지 않게 한다 (run_preprocess.py 가 처리).
"""

from __future__ import annotations

import pandas as pd
from konlpy.tag import Okt
from tqdm import tqdm

from . import config


# ──────────────── 불용어 로딩 ────────────────

def _load_stopwords() -> set[str]:
    """stopwords.txt 를 set 으로.

    "#" 주석과 빈 줄 무시.
    """
    words: set[str] = set()
    with config.STOPWORDS_PATH.open(encoding="utf-8") as f:
        for line in f:
            w = line.strip()
            if not w or w.startswith("#"):
                continue
            words.add(w)
    return words


_STOPWORDS: set[str] | None = None
_OKT: Okt | None = None


def _stopwords() -> set[str]:
    global _STOPWORDS
    if _STOPWORDS is None:
        _STOPWORDS = _load_stopwords()
        print(f"[token] stopwords: {len(_STOPWORDS)}개")
    return _STOPWORDS


def _okt() -> Okt:
    """Okt 인스턴스 lazy init. 첫 호출에서 JVM 띄우느라 1~2초 소요."""
    global _OKT
    if _OKT is None:
        _OKT = Okt()
    return _OKT


# ──────────────── 토큰화 ────────────────

def _tokenize_one(text: str) -> list[str]:
    """문장 하나를 토큰 리스트로.

    필터 순서:
        1) Okt morphs (stem 적용)
        2) 불용어 제거
        3) 1글자 토큰 제거 (화이트리스트 예외)
    """
    tokens = _okt().morphs(text, stem=config.OKT_STEM)

    stop = _stopwords()
    whitelist = config.SINGLE_CHAR_WHITELIST

    out: list[str] = []
    for t in tokens:
        if t in stop:
            continue
        if config.DROP_SINGLE_CHAR and len(t) == 1 and t not in whitelist:
            continue
        out.append(t)
    return out


def tokenize(df: pd.DataFrame) -> pd.DataFrame:
    """clean_review 컬럼을 토큰화해 tokens 컬럼 추가.

    이어서 토큰 수 < MIN_TOKEN_LEN 인 행을 제거한다.
    이 단계까지 살아남은 리뷰가 최종 학습/평가 후보.
    """
    df = df.copy()

    # tqdm.pandas() 등록 후 progress_apply 로 진행률 표시 (수업 0526 방식)
    tqdm.pandas(desc="Okt 형태소 분석")
    df["tokens"] = df["clean_review"].progress_apply(_tokenize_one)

    before = len(df)
    df = df[df["tokens"].apply(len) >= config.MIN_TOKEN_LEN]
    dropped = before - len(df)
    print(
        f"[token] 토큰수<{config.MIN_TOKEN_LEN} 제거: "
        f"{before:,} → {len(df):,}  (-{dropped:,})"
    )

    # 검수용 문자열 컬럼 (parquet 외에 csv 로 떨굴 때 사람이 읽기 쉬움)
    df["tokens_str"] = df["tokens"].apply(" ".join)

    # 평균 토큰 길이 — RNN 의 max_len 정할 때 참고
    lens = df["tokens"].apply(len)
    print(
        f"[token] 토큰 길이  mean={lens.mean():.1f}  "
        f"median={lens.median():.0f}  p95={lens.quantile(0.95):.0f}  "
        f"max={lens.max()}"
    )

    return df.reset_index(drop=True)
