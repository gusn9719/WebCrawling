"""Train a Keras BiLSTM sentiment classifier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.utils.class_weight import compute_class_weight

from sentiment.data import CLASS_NAMES, LABEL_TO_ID, load_train_val, print_dataset_summary
from sentiment.metrics import save_evaluation


MAX_TOKENS = 80_000
SEQUENCE_LENGTH = 120
EMBEDDING_DIM = 128
LSTM_UNITS = 64
DROPOUT_RATE = 0.4
BATCH_SIZE = 256
EPOCHS = 10
RANDOM_STATE = 42
MODELS_DIR = Path("models")
REPORTS_DIR = Path("reports")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a BiLSTM sentiment model.")
    parser.add_argument(
        "--class-weight",
        choices=("none", "balanced"),
        default="balanced",
        help="Whether to apply balanced class weights.",
    )
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    return parser.parse_args()


def build_model(tf, vectorizer):
    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(1,), dtype=tf.string),
            vectorizer,
            tf.keras.layers.Embedding(MAX_TOKENS, EMBEDDING_DIM, mask_zero=True),
            tf.keras.layers.Bidirectional(tf.keras.layers.LSTM(LSTM_UNITS)),
            tf.keras.layers.Dropout(DROPOUT_RATE),
            tf.keras.layers.Dense(len(CLASS_NAMES), activation="softmax"),
        ]
    )
    model.compile(
        optimizer="adam",
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def make_class_weight(mode: str, labels):
    if mode == "none":
        return None
    weights = compute_class_weight(
        class_weight="balanced",
        classes=pd.Series(sorted(LABEL_TO_ID.values())).to_numpy(),
        y=labels,
    )
    return {class_id: float(weight) for class_id, weight in enumerate(weights)}


def save_vocab(vectorizer) -> None:
    vocab_path = MODELS_DIR / "lstm_vocab.txt"
    vocab_path.write_text("\n".join(vectorizer.get_vocabulary()), encoding="utf-8")


def save_label_map() -> None:
    label_path = MODELS_DIR / "label_map.json"
    label_path.write_text(
        json.dumps(LABEL_TO_ID, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    import tensorflow as tf

    tf.keras.utils.set_random_seed(RANDOM_STATE)

    train, val = load_train_val()
    print_dataset_summary(train, val)
    print("Missing/empty text policy: rows are removed before training.")

    vectorizer = tf.keras.layers.TextVectorization(
        max_tokens=MAX_TOKENS,
        output_mode="int",
        output_sequence_length=SEQUENCE_LENGTH,
        standardize=None,
    )
    vectorizer.adapt(train.texts)
    save_vocab(vectorizer)
    save_label_map()

    model = build_model(tf, vectorizer)
    model_name = f"lstm_{args.class_weight}"
    model_path = MODELS_DIR / f"{model_name}.keras"

    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=2,
            restore_best_weights=True,
        ),
        tf.keras.callbacks.ModelCheckpoint(
            filepath=model_path,
            monitor="val_loss",
            save_best_only=True,
        ),
    ]

    class_weight = make_class_weight(args.class_weight, train.labels)
    history = model.fit(
        train.texts,
        train.labels,
        validation_data=(val.texts, val.labels),
        epochs=args.epochs,
        batch_size=args.batch_size,
        callbacks=callbacks,
        class_weight=class_weight,
        verbose=1,
    )

    if not model_path.exists():
        model.save(model_path)

    probabilities = model.predict(val.texts, batch_size=args.batch_size)
    predictions = probabilities.argmax(axis=1)
    metrics = save_evaluation(val.labels, predictions, model_name)

    history_frame = pd.DataFrame(history.history)
    history_frame.to_csv(REPORTS_DIR / f"{model_name}_history.csv", index=False)

    print(
        f"{model_name}: accuracy={metrics['accuracy']:.4f}, "
        f"macro_f1={metrics['macro_f1']:.4f}, "
        f"neutral_recall={metrics['neutral_recall']:.4f}"
    )


if __name__ == "__main__":
    main()

