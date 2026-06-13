"""전처리 파이프라인 진입점.

크롤러 산출물(JSONL)을 감성분석 학습 데이터로 정리한다.

흐름:
    io.load_reviews                         JSONL → DataFrame
        ↓
    cleaning.clean                          결측·정제·중복·길이 필터
        ↓
    labeling.label_by_rating_and_text       별점 후보 라벨 + 본문 감성 단서
        ↓
    ambiguous 분리                          학습 기본 흐름에서 제외
        ↓
    tokenize.tokenize                       Okt 형태소 분석 + 불용어
        ↓
    split.train_val                         stratified 8:2
        ↓
    저장                                    parquet + preview csv

실행:
    python run_preprocess.py
    python run_preprocess.py --categories skincare
    python run_preprocess.py --sample 5000
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

from preprocess import cleaning, config, labeling, split, tokenize
from preprocess import io as io_mod


def _save(df: pd.DataFrame, path: Path, fmt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "parquet":
        df.to_parquet(path, index=False)
    elif fmt == "csv":
        df.drop(columns=[c for c in ["tokens"] if c in df.columns]).to_csv(
            path, index=False, encoding="utf-8-sig"
        )
    else:
        raise ValueError(f"지원하지 않는 저장 형식: {fmt}")
    print(f"[save] {path}  ({len(df):,} 건)")


def _label_dist(df: pd.DataFrame) -> dict[str, int]:
    counts = df["sentiment_label"].value_counts().to_dict()
    return {label: int(counts.get(label, 0)) for label in ["negative", "neutral", "positive"]}


def _print_conflict_examples(ambiguous: pd.DataFrame) -> None:
    examples = labeling.conflict_examples(ambiguous, n=5)
    print("\n[summary] 별점과 텍스트가 충돌한 대표 예시 5개:")
    if examples.empty:
        print("  충돌 예시 없음")
        return

    for idx, row in examples.iterrows():
        text = str(row["review_text"]).replace("\n", " ").replace("\r", " ")
        if len(text) > 120:
            text = text[:117] + "..."
        print(
            f"  {idx + 1}. rating={row['rating']} "
            f"rating_label={row['rating_label']} "
            f"text_rule_label={row['text_rule_label']} "
            f"reason={row['ambiguous_reason']}"
        )
        print(f"     {text}")


def _print_summary(
    total_reviews: int,
    cleaned_reviews: int,
    confirmed: pd.DataFrame,
    ambiguous: pd.DataFrame,
    splits: dict[str, pd.DataFrame],
) -> None:
    label_total = len(confirmed) + len(ambiguous)
    ambiguous_ratio = len(ambiguous) / label_total * 100 if label_total else 0.0

    print("\n=== 전처리 결과 요약 ===")
    print(f"전체 리뷰 수: {total_reviews:,}")
    print(f"중복 제거 후 리뷰 수: {cleaned_reviews:,}")
    all_labeled = pd.concat([confirmed, ambiguous], ignore_index=True)
    print("별점 기준 라벨 분포:")
    for label, count in all_labeled["rating_label"].value_counts().sort_index().items():
        print(f"  {label}: {count:,}")
    print("텍스트 규칙 기준 라벨 분포:")
    for label, count in all_labeled["text_rule_label"].value_counts().sort_index().items():
        print(f"  {label}: {count:,}")
    print(f"최종 학습 사용 데이터 수: {len(confirmed):,}")
    print(f"ambiguous로 제외된 데이터 수: {len(ambiguous):,}")
    print(f"ambiguous 비율: {ambiguous_ratio:.1f}%")
    print("최종 sentiment_label 분포:")
    for label, count in _label_dist(confirmed).items():
        print(f"  {label}: {count:,}")
    print(f"train 데이터 수: {len(splits['train']):,}")
    print(f"validation 데이터 수: {len(splits['val']):,}")
    print(f"train 라벨 분포: {_label_dist(splits['train'])}")
    print(f"validation 라벨 분포: {_label_dist(splits['val'])}")

    _print_conflict_examples(ambiguous)


def main() -> None:
    parser = argparse.ArgumentParser(description="올리브영 리뷰 전처리 파이프라인")
    parser.add_argument(
        "--categories",
        nargs="+",
        default=None,
        help="처리할 카테고리. 미지정시 전체.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="앞에서 N건만 잘라서 처리 (개발/디버그용)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=config.OUTPUT_DIR,
        help=f"출력 디렉토리 (기본: {config.OUTPUT_DIR})",
    )
    args = parser.parse_args()

    t0 = time.time()

    print("\n=== [1/5] 로딩 ===")
    df = io_mod.load_reviews(categories=args.categories)
    total_reviews = len(df)
    if args.sample:
        df = df.head(args.sample)
        total_reviews = len(df)
        print(f"[main] --sample={args.sample} 적용: {len(df):,} 건")

    print("\n=== [2/5] 정제 ===")
    df = cleaning.clean(df)
    cleaned_reviews = len(df)

    print("\n=== [3/5] 라벨링 (별점 후보 + 본문 감성 단서) ===")
    confirmed, ambiguous = labeling.label_by_rating_and_text(df)

    print("\n=== [4/5] 토큰화 및 8:2 분리 ===")
    confirmed = tokenize.tokenize(confirmed)
    splits = split.train_val(confirmed)

    print("\n=== [5/5] 저장 ===")
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    _save(splits["train"], out / "train.parquet", "parquet")
    _save(splits["val"], out / "val.parquet", "parquet")
    _save(ambiguous, out / "ambiguous.parquet", "parquet")
    _save(splits["train"].head(2000), out / "train_preview.csv", "csv")
    _save(ambiguous.head(2000), out / "ambiguous_preview.csv", "csv")

    _print_summary(total_reviews, cleaned_reviews, confirmed, ambiguous, splits)
    print(f"\n[main] 전체 소요: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
