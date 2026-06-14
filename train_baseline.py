"""Train TF-IDF + LogisticRegression sentiment baselines."""

from __future__ import annotations

from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from sentiment.data import load_train_val, print_dataset_summary
from sentiment.metrics import save_evaluation


MAX_FEATURES = 100_000
NGRAM_RANGE = (1, 2)
MIN_DF = 2
MAX_DF = 0.95
RANDOM_STATE = 42
MAX_ITER = 1_000
MODELS_DIR = Path("models")


def train_one_model(name: str, class_weight, train_x, train_y, val_x, val_y) -> None:
    model = LogisticRegression(
        class_weight=class_weight,
        max_iter=MAX_ITER,
        random_state=RANDOM_STATE,
        solver="lbfgs",
    )
    model.fit(train_x, train_y)
    predictions = model.predict(val_x)

    model_path = MODELS_DIR / f"baseline_logreg_{name}.joblib"
    joblib.dump(model, model_path)

    metrics = save_evaluation(val_y, predictions, f"baseline_{name}")
    print(
        f"baseline_{name}: accuracy={metrics['accuracy']:.4f}, "
        f"macro_f1={metrics['macro_f1']:.4f}, "
        f"neutral_recall={metrics['neutral_recall']:.4f}"
    )


def main() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    train, val = load_train_val()
    print_dataset_summary(train, val)
    print("Missing/empty text policy: rows are removed before training.")

    vectorizer = TfidfVectorizer(
        max_features=MAX_FEATURES,
        ngram_range=NGRAM_RANGE,
        min_df=MIN_DF,
        max_df=MAX_DF,
    )
    train_x = vectorizer.fit_transform(train.texts)
    val_x = vectorizer.transform(val.texts)
    joblib.dump(vectorizer, MODELS_DIR / "tfidf_vectorizer.joblib")

    train_one_model("none", None, train_x, train.labels, val_x, val.labels)
    train_one_model("balanced", "balanced", train_x, train.labels, val_x, val.labels)


if __name__ == "__main__":
    main()
