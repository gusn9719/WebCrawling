"""LSTM v2 + Transformer v2 예측을 사전 계산해 parquet으로 저장.

한 번만 실행하면 앱에서 즉시 로딩 가능 (런타임 추론 불필요).

Usage:
    C:\\Users\\user\\anaconda3\\envs\\oliveyoung\\python.exe precompute_preds.py
    C:\\Users\\user\\anaconda3\\envs\\oliveyoung\\python.exe precompute_preds.py --model lstm
    C:\\Users\\user\\anaconda3\\envs\\oliveyoung\\python.exe precompute_preds.py --model transformer
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "preprocessed_v3"
MODEL_DIR = BASE_DIR / "models"

ID2LABEL = {0: "negative", 1: "neutral", 2: "positive"}


def load_data() -> pd.DataFrame:
    print("데이터 로딩 중...")
    train = pd.read_parquet(DATA_DIR / "train.parquet")
    val = pd.read_parquet(DATA_DIR / "val.parquet")
    df = pd.concat([train, val], ignore_index=True)
    print(f"  총 {len(df):,}행")
    return df


def run_lstm(df: pd.DataFrame) -> None:
    out_path = DATA_DIR / "lstm_v3_preds.parquet"
    print("\n[LSTM v3] 추론 시작...")
    import tensorflow as tf  # type: ignore

    model = tf.keras.models.load_model(str(MODEL_DIR / "lstm_final_v3.keras"))
    texts = df["tokens_str"].fillna("").tolist()
    texts_tf = tf.constant(texts, dtype=tf.string)
    texts_tf = tf.reshape(texts_tf, (-1, 1))

    t0 = time.time()
    proba = model.predict(texts_tf, batch_size=1024, verbose=1)
    elapsed = time.time() - t0
    print(f"  완료: {elapsed:.0f}초")

    preds = [ID2LABEL[i] for i in proba.argmax(axis=1)]
    result = pd.DataFrame({"review_id": df["review_id"].tolist(), "lstm_v3_pred": preds})
    result.to_parquet(out_path, index=False)
    print(f"  저장: {out_path}")
    print(f"  분포: {result['lstm_v3_pred'].value_counts().to_dict()}")


def run_transformer(df: pd.DataFrame) -> None:
    out_path = DATA_DIR / "transformer_v3_preds.parquet"
    print("\n[Transformer v3] 추론 시작...")
    import torch  # type: ignore
    from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore

    path = str(MODEL_DIR / "transformer_final_v3")
    tokenizer = AutoTokenizer.from_pretrained(path)
    model = AutoModelForSequenceClassification.from_pretrained(path)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()
    print(f"  디바이스: {device}")

    texts = df["clean_review"].fillna("").tolist()
    ids = df["review_id"].tolist()
    total = len(texts)
    batch_size = 64
    preds: list[str] = []

    t0 = time.time()
    for i in range(0, total, batch_size):
        batch = texts[i : i + batch_size]
        inputs = tokenizer(batch, return_tensors="pt", truncation=True, max_length=128, padding=True)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            logits = model(**inputs).logits
        pred_ids = logits.argmax(dim=-1).cpu().numpy()
        preds.extend(ID2LABEL[int(p)] for p in pred_ids)
        if (i // batch_size) % 50 == 0:
            pct = (i + len(batch)) / total * 100
            elapsed = time.time() - t0
            print(f"  {pct:.1f}% ({i + len(batch):,}/{total:,}) / {elapsed:.0f}s")

    elapsed = time.time() - t0
    print(f"  완료: {elapsed:.0f}초 ({elapsed/60:.1f}분)")

    result = pd.DataFrame({"review_id": ids, "transformer_v3_pred": preds})
    result.to_parquet(out_path, index=False)
    print(f"  저장: {out_path}")
    print(f"  분포: {result['transformer_v3_pred'].value_counts().to_dict()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["lstm", "transformer", "all"], default="all")
    args = parser.parse_args()

    df = load_data()

    if args.model in ("lstm", "all"):
        run_lstm(df)

    if args.model in ("transformer", "all"):
        run_transformer(df)

    print("\n모든 사전 계산 완료. 앱을 재시작하면 즉시 로딩됩니다.")


if __name__ == "__main__":
    main()
