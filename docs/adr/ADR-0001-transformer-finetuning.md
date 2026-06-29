# ADR-0001: Transformer Fine-Tuning Baseline

## Status

Accepted

## Context

The project already has TF-IDF LogisticRegression and BiLSTM baselines for
3-class review sentiment classification. The next experiment needs a modern NLP
baseline that can use pretrained Korean language representations and capture
review context better than bag-of-words or an in-project LSTM trained from
scratch.

## Decision

Add a Hugging Face Transformers + PyTorch training path in `train_transformer.py`.
Use `klue/bert-base` as the first default checkpoint, `clean_review` as the
default text input, and save evaluation artifacts through the existing
`sentiment.metrics.save_evaluation()` reporting flow.

Default hyperparameters:

- `model_name=klue/bert-base`
- `text_column=clean_review`
- `max_length=160`
- `epochs=3`
- `batch_size=16`
- `learning_rate=2e-5`
- `weight_decay=0.01`
- `warmup_ratio=0.1`
- `class_weight=balanced`
- `metric_for_best_model=macro_f1`

## Reason

- Transformer-based pretrained encoders are the strongest practical next
  baseline for NLP text classification and sentiment analysis.
- `klue/bert-base` is a Korean BERT-family checkpoint, so it is a reasonable
  first model for Korean cosmetic review text.
- `clean_review` keeps natural Korean word order for the pretrained tokenizer;
  `tokens_str` is better suited to TF-IDF/LSTM experiments that use Okt tokens.
- `max_length=160` captures most short product reviews while keeping memory use
  lower than a 512-token maximum.
- `epochs=3` is a conservative fine-tuning start for weak rule-based labels and
  limits overfitting.
- `learning_rate=2e-5`, `batch_size=16`, `weight_decay=0.01`, and
  `warmup_ratio=0.1` follow common BERT fine-tuning practice.
- `class_weight=balanced` keeps the Transformer experiment comparable to the
  existing imbalance experiments and gives minority `neutral` examples enough
  loss signal.
- `macro_f1` is selected as the best-model metric because accuracy is misleading
  under the current positive-heavy class distribution.

## Alternatives Considered

- Continue only with BiLSTM.
  - Rejected because it trains representations from this dataset only and has
    not yet improved over the balanced TF-IDF baseline.
- Use `tokens_str` as the Transformer input.
  - Rejected because pretrained tokenizers expect natural text, not whitespace
    joined Okt morphemes.
- Use `beomi/KcELECTRA-base` as the first default.
  - Deferred. It may be useful for Korean review/comment style text, but
    `klue/bert-base` is a conservative first baseline.
- Train with no class weights.
  - Rejected as the default because previous experiments showed severe neutral
    recall collapse without imbalance handling.

## Consequences

### Positive

- Adds a modern, comparable NLP baseline without changing the existing dataset
  format.
- Reuses the same report files as baseline and LSTM experiments.
- Records hyperparameter rationale in `reports/*_hyperparameters.json`.

### Negative / Trade-offs

- First run downloads a pretrained model and requires network access.
- Training is slower and more memory-intensive than TF-IDF and BiLSTM.
- Weak rule-based labels still limit final model quality, even with a stronger
  architecture.

## Related Files

- `train_transformer.py`
- `requirements.txt`
- `README.md`
- `sentiment/metrics.py`
- `sentiment/data.py`

## Date

2026-06-18
