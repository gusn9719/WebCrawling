"""Fine-tune a Transformer sentiment classifier with Hugging Face."""

from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from sklearn.utils.class_weight import compute_class_weight

from sentiment.data import CLASS_NAMES, ID_TO_LABEL, LABEL_TO_ID, validate_labels
from sentiment.metrics import save_evaluation


DEFAULT_MODEL_NAME = "klue/bert-base"
DEFAULT_TEXT_COLUMN = "clean_review"
MAX_LENGTH = 160
BATCH_SIZE = 16
EPOCHS = 3
LEARNING_RATE = 2e-5
WEIGHT_DECAY = 0.01
WARMUP_RATIO = 0.1
RANDOM_STATE = 42
MODELS_DIR = Path("models")
REPORTS_DIR = Path("reports")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fine-tune a Transformer model for 3-class sentiment analysis."
    )
    parser.add_argument("--train-path", default="preprocessed/train.parquet")
    parser.add_argument("--val-path", default="preprocessed/val.parquet")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--text-column", default=DEFAULT_TEXT_COLUMN)
    parser.add_argument("--max-length", type=int, default=MAX_LENGTH)
    parser.add_argument("--epochs", type=float, default=EPOCHS)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--learning-rate", type=float, default=LEARNING_RATE)
    parser.add_argument("--weight-decay", type=float, default=WEIGHT_DECAY)
    parser.add_argument("--warmup-ratio", type=float, default=WARMUP_RATIO)
    parser.add_argument(
        "--class-weight",
        choices=("none", "balanced"),
        default="balanced",
        help="Whether to apply balanced class weights in cross entropy loss.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Use the first N rows from each split for a fast smoke test.",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Prefix for model and report artifacts.",
    )
    parser.add_argument(
        "--fp16",
        action="store_true",
        help="Use mixed precision when CUDA is available.",
    )
    parser.add_argument(
        "--resume-from-checkpoint",
        default=None,
        help="Path to a checkpoint directory to resume training from.",
    )
    return parser.parse_args()


def safe_model_name(model_name: str) -> str:
    return model_name.replace("/", "-").replace("\\", "-")


def load_text_label_frame(
    path: str | Path,
    text_column: str,
    sample: int | None,
) -> tuple[list[str], np.ndarray, int]:
    split_path = Path(path)
    if not split_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {split_path}")

    frame = pd.read_parquet(split_path)
    validate_labels(frame, split_path)
    if text_column not in frame.columns:
        raise ValueError(f"{split_path} must contain text column: {text_column}")

    text_values = frame[text_column]
    missing_mask = text_values.isna()
    non_missing_text = text_values[~missing_mask].astype(str).str.strip()
    empty_mask = non_missing_text.eq("")
    valid_index = non_missing_text.index[~empty_mask]

    filtered = frame.loc[valid_index]
    texts = non_missing_text.loc[valid_index]
    if sample is not None:
        filtered = filtered.head(sample)
        texts = texts.loc[filtered.index]

    labels = filtered["sentiment_id"].astype(int).to_numpy()
    dropped_rows = int(missing_mask.sum() + empty_mask.sum())
    return texts.tolist(), labels, dropped_rows


def make_dataset(torch, tokenizer, texts: list[str], labels: np.ndarray, max_length: int):
    encodings = tokenizer(texts, truncation=True, max_length=max_length)

    class ReviewDataset(torch.utils.data.Dataset):
        def __len__(self) -> int:
            return len(labels)

        def __getitem__(self, index: int) -> dict:
            item = {key: torch.tensor(value[index]) for key, value in encodings.items()}
            item["labels"] = torch.tensor(int(labels[index]), dtype=torch.long)
            return item

    return ReviewDataset()


def make_class_weights(mode: str, labels: np.ndarray) -> np.ndarray | None:
    if mode == "none":
        return None
    weights = compute_class_weight(
        class_weight="balanced",
        classes=np.array(sorted(LABEL_TO_ID.values())),
        y=labels,
    )
    return weights.astype("float32")


def make_weighted_trainer_class(torch, Trainer):
    class WeightedTrainer(Trainer):
        def __init__(self, *args, class_weights=None, **kwargs):
            super().__init__(*args, **kwargs)
            if class_weights is None:
                self.class_weights = None
            else:
                self.class_weights = torch.tensor(class_weights, dtype=torch.float32)

        def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
            labels = inputs.pop("labels")
            outputs = model(**inputs)
            logits = outputs.logits
            weights = (
                self.class_weights.to(logits.device)
                if self.class_weights is not None
                else None
            )
            loss_fct = torch.nn.CrossEntropyLoss(weight=weights)
            loss = loss_fct(logits.view(-1, model.config.num_labels), labels.view(-1))
            return (loss, outputs) if return_outputs else loss

    return WeightedTrainer


def make_training_arguments(TrainingArguments, args, run_name: str, use_fp16: bool):
    output_dir = MODELS_DIR / run_name
    params = inspect.signature(TrainingArguments.__init__).parameters
    kwargs = {
        "output_dir": str(output_dir),
        "learning_rate": args.learning_rate,
        "per_device_train_batch_size": args.batch_size,
        "per_device_eval_batch_size": args.batch_size,
        "num_train_epochs": args.epochs,
        "weight_decay": args.weight_decay,
        "load_best_model_at_end": True,
        "metric_for_best_model": "eval_loss",
        "greater_is_better": False,
        "save_total_limit": 2,
        "seed": RANDOM_STATE,
        "report_to": [],
    }

    strategy_key = "eval_strategy" if "eval_strategy" in params else "evaluation_strategy"
    kwargs[strategy_key] = "epoch"
    if "save_strategy" in params:
        kwargs["save_strategy"] = "epoch"
    if "logging_strategy" in params:
        kwargs["logging_strategy"] = "epoch"

    if "warmup_ratio" in params:
        kwargs["warmup_ratio"] = args.warmup_ratio
    if "fp16" in params:
        kwargs["fp16"] = use_fp16
    # Prevent Windows DataLoader multiprocessing deadlock
    if "dataloader_num_workers" in params:
        kwargs["dataloader_num_workers"] = 0

    supported_kwargs = {key: value for key, value in kwargs.items() if key in params}
    return TrainingArguments(**supported_kwargs)


def compute_metrics(eval_pred) -> dict[str, float]:
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    macro_precision, macro_recall, macro_f1, _ = precision_recall_fscore_support(
        labels,
        predictions,
        labels=sorted(ID_TO_LABEL),
        average="macro",
        zero_division=0,
    )
    _, class_recall, class_f1, _ = precision_recall_fscore_support(
        labels,
        predictions,
        labels=sorted(ID_TO_LABEL),
        average=None,
        zero_division=0,
    )
    return {
        "accuracy": float(accuracy_score(labels, predictions)),
        "macro_precision": float(macro_precision),
        "macro_recall": float(macro_recall),
        "macro_f1": float(macro_f1),
        "negative_recall": float(class_recall[LABEL_TO_ID["negative"]]),
        "neutral_recall": float(class_recall[LABEL_TO_ID["neutral"]]),
        "positive_recall": float(class_recall[LABEL_TO_ID["positive"]]),
        "negative_f1": float(class_f1[LABEL_TO_ID["negative"]]),
        "neutral_f1": float(class_f1[LABEL_TO_ID["neutral"]]),
        "positive_f1": float(class_f1[LABEL_TO_ID["positive"]]),
    }


def save_hyperparameter_record(args, run_name: str, use_fp16: bool) -> None:
    record = {
        "run_name": run_name,
        "model_name": args.model_name,
        "text_column": args.text_column,
        "max_length": args.max_length,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "warmup_ratio": args.warmup_ratio,
        "class_weight": args.class_weight,
        "fp16": use_fp16,
        "rationale": {
            "model_name": "Use a Korean BERT-family checkpoint as the first Transformer baseline for Korean review text.",
            "text_column": "Use clean_review because pretrained Transformer tokenizers should see natural Korean text rather than Okt token strings.",
            "max_length": "160 tokens keeps most short product reviews while reducing memory cost versus the 512-token maximum.",
            "epochs": "3 epochs is a common fine-tuning starting point and limits overfitting on weak rule-based labels.",
            "batch_size": "16 is a conservative BERT-base batch size for typical single-GPU memory; reduce to 8 if memory is tight.",
            "learning_rate": "2e-5 is a standard small fine-tuning learning rate for pretrained BERT-style encoders.",
            "weight_decay": "0.01 adds mild regularization for the classification head and encoder weights.",
            "warmup_ratio": "0.1 stabilizes early fine-tuning before applying the full learning rate.",
            "class_weight": "balanced keeps the comparison aligned with existing imbalance experiments and protects minority neutral examples.",
        },
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{run_name}_hyperparameters.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def print_split_summary(name: str, labels: np.ndarray, dropped_rows: int) -> None:
    counts = {
        CLASS_NAMES[label_id]: int((labels == label_id).sum())
        for label_id in sorted(ID_TO_LABEL)
    }
    print(f"{name}: rows={len(labels)}, dropped_missing_or_empty_text_rows={dropped_rows}")
    print(f"{name} label distribution: {counts}")


def main() -> None:
    args = parse_args()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    import torch
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        DataCollatorWithPadding,
        EarlyStoppingCallback,
        Trainer,
        TrainingArguments,
        set_seed,
    )

    set_seed(RANDOM_STATE)
    use_fp16 = bool(args.fp16 and torch.cuda.is_available())
    run_name = args.run_name or f"transformer_{safe_model_name(args.model_name)}_{args.class_weight}"

    train_texts, train_labels, train_dropped = load_text_label_frame(
        args.train_path, args.text_column, args.sample
    )
    val_texts, val_labels, val_dropped = load_text_label_frame(
        args.val_path, args.text_column, args.sample
    )
    print("Text feature policy: use clean_review by default for Transformer tokenizers.")
    print("Rating/score/star columns are not used as model features.")
    print_split_summary("train", train_labels, train_dropped)
    print_split_summary("validation", val_labels, val_dropped)

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    train_dataset = make_dataset(torch, tokenizer, train_texts, train_labels, args.max_length)
    val_dataset = make_dataset(torch, tokenizer, val_texts, val_labels, args.max_length)

    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_name,
        num_labels=len(CLASS_NAMES),
        id2label={label_id: label for label_id, label in ID_TO_LABEL.items()},
        label2id={label: label_id for label, label_id in LABEL_TO_ID.items()},
    )

    trainer_cls = make_weighted_trainer_class(torch, Trainer)
    training_args = make_training_arguments(TrainingArguments, args, run_name, use_fp16)
    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    trainer_kwargs = {
        "model": model,
        "args": training_args,
        "train_dataset": train_dataset,
        "eval_dataset": val_dataset,
        "data_collator": data_collator,
        "compute_metrics": compute_metrics,
        "callbacks": [EarlyStoppingCallback(early_stopping_patience=2)],
        "class_weights": make_class_weights(args.class_weight, train_labels),
    }
    trainer_params = inspect.signature(Trainer.__init__).parameters
    if "processing_class" in trainer_params:
        trainer_kwargs["processing_class"] = tokenizer
    else:
        trainer_kwargs["tokenizer"] = tokenizer

    trainer = trainer_cls(**trainer_kwargs)
    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)
    trainer.save_model(str(MODELS_DIR / run_name))
    tokenizer.save_pretrained(str(MODELS_DIR / run_name))

    predictions_output = trainer.predict(val_dataset)
    predictions = np.argmax(predictions_output.predictions, axis=-1)
    metrics = save_evaluation(val_labels, predictions, run_name)

    history_frame = pd.DataFrame(trainer.state.log_history)
    history_frame.to_csv(REPORTS_DIR / f"{run_name}_history.csv", index=False)
    save_hyperparameter_record(args, run_name, use_fp16)

    print(
        f"{run_name}: accuracy={metrics['accuracy']:.4f}, "
        f"macro_f1={metrics['macro_f1']:.4f}, "
        f"neutral_recall={metrics['neutral_recall']:.4f}"
    )


if __name__ == "__main__":
    main()
