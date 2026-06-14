"""Shared evaluation and report saving utilities."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
)

from sentiment.data import CLASS_NAMES, ID_TO_LABEL


def save_evaluation(
    y_true,
    y_pred,
    report_prefix: str,
    reports_dir: str | Path = "reports",
) -> dict:
    """Save metrics, classification report, and confusion matrix."""
    output_dir = Path(reports_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    labels = sorted(ID_TO_LABEL)
    macro_precision, macro_recall, macro_f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=labels,
        average="macro",
        zero_division=0,
    )
    _, _, weighted_f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=labels,
        average="weighted",
        zero_division=0,
    )

    report_dict = classification_report(
        y_true,
        y_pred,
        labels=labels,
        target_names=CLASS_NAMES,
        output_dict=True,
        zero_division=0,
    )
    report_frame = pd.DataFrame(report_dict).transpose()

    matrix = confusion_matrix(y_true, y_pred, labels=labels)
    matrix_frame = pd.DataFrame(matrix, index=CLASS_NAMES, columns=CLASS_NAMES)

    predicted_distribution = {
        ID_TO_LABEL[label_id]: int((pd.Series(y_pred) == label_id).sum())
        for label_id in labels
    }

    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_precision": float(macro_precision),
        "macro_recall": float(macro_recall),
        "macro_f1": float(macro_f1),
        "weighted_f1": float(weighted_f1),
        "negative_recall": float(report_dict["negative"]["recall"]),
        "neutral_recall": float(report_dict["neutral"]["recall"]),
        "predicted_label_distribution": predicted_distribution,
        "class_metrics": {
            class_name: {
                "precision": float(report_dict[class_name]["precision"]),
                "recall": float(report_dict[class_name]["recall"]),
                "f1": float(report_dict[class_name]["f1-score"]),
                "support": int(report_dict[class_name]["support"]),
            }
            for class_name in CLASS_NAMES
        },
    }

    metrics_path = output_dir / f"{report_prefix}_metrics.json"
    report_path = output_dir / f"{report_prefix}_classification_report.csv"
    matrix_path = output_dir / f"{report_prefix}_confusion_matrix.csv"

    metrics_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_frame.to_csv(report_path, encoding="utf-8")
    matrix_frame.to_csv(matrix_path, encoding="utf-8")

    return metrics

