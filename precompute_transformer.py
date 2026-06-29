"""Transformer v2 예측을 사전 계산해 preprocessed_v2/transformer_v2_preds.parquet 에 저장.

약 20~25분 소요 (CPU 기준). 한 번만 실행하면 앱에서 즉시 로딩 가능.

Usage:
    python precompute_transformer.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "preprocessed_v2"
MODEL_DIR = BASE_DIR / "models"
OUT_PATH = DATA_DIR / "transformer_v2_preds.parquet"

ID2LABEL = {0: "negative", 1: "neutral", 2: "positive"}
BATCH_SIZE = 64
MAX_LENGTH = 128


def predict_batch(texts: list[str], model, tokenizer, device) -> list[str]:
    inputs = tokenizer(
        texts,
        return_tensors="pt",
        truncation=True,
        max_length=MAX_LENGTH,
        padding=True,
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        logits = model(**inputs).logits
    pred_ids = logits.argmax(dim=-1).cpu().numpy()
    return [ID2LABEL[i] for i in pred_ids]


def main() -> None:
    print("모델 로딩 중...")
    path = str(MODEL_DIR / "transformer_final_v2")
    tokenizer = AutoTokenizer.from_pretrained(path)
    model = AutoModelForSequenceClassification.from_pretrained(path)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()
    print(f"  디바이스: {device}")

    print("데이터 로딩 중...")
    train = pd.read_parquet(DATA_DIR / "train.parquet", columns=["review_id", "clean_review"])
    val = pd.read_parquet(DATA_DIR / "val.parquet", columns=["review_id", "clean_review"])
    df = pd.concat([train, val], ignore_index=True)
    texts = df["clean_review"].fillna("").tolist()
    ids = df["review_id"].tolist()
    total = len(texts)
    print(f"  총 {total:,}행")

    print("추론 시작...")
    preds: list[str] = []
    for i in range(0, total, BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        preds.extend(predict_batch(batch, model, tokenizer, device))
        if (i // BATCH_SIZE) % 50 == 0:
            pct = (i + len(batch)) / total * 100
            print(f"  {pct:.1f}% ({i + len(batch):,}/{total:,})")

    print("저장 중...")
    result = pd.DataFrame({"review_id": ids, "transformer_pred": preds})
    result.to_parquet(OUT_PATH, index=False)
    print(f"완료: {OUT_PATH}")
    print(f"  분포: {result['transformer_pred'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
