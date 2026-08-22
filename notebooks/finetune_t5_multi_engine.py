"""
finetune_t5_multi_engine.py

Continues fine-tuning the existing Oracle T5 model on the multi-engine
dataset (data/finetune/train_v2.jsonl + val_v2.jsonl), produced by
build_finetune_dataset_v2.py.

KEY CONSTRAINT (from PROGRESS.md and BUILD_PLAN):
    Must start from models/oracle_log_t5_model/ (the already fine-tuned
    Oracle checkpoint), NOT raw FLAN-T5-base. This preserves all Oracle
    learning while adding Postgres/MySQL knowledge.

BUGS PROACTIVELY FIXED (from PROGRESS.md lesson log):
    1. Regex-based structured output parsing in generator.py (already done).
    2. DataCollatorForSeq2Seq with padding=True (avoids batch shape errors).
    3. Use `processing_class` instead of `tokenizer` in Seq2SeqTrainer
       (avoids TypeError in transformers >= 4.46).
    4. Code-level split (already done in build_finetune_dataset_v2.py).

Usage:
    python notebooks/finetune_t5_multi_engine.py
    python notebooks/finetune_t5_multi_engine.py --epochs 3 --batch-size 4
    python notebooks/finetune_t5_multi_engine.py --dry-run   # smoke-test only
"""

import argparse
import json
import os
import sys

# ── Hyperparameters (tuned from prior session results) ──────────────────────
DEFAULT_EPOCHS = 3
DEFAULT_BATCH_SIZE = 4
DEFAULT_MAX_INPUT_LEN = 512
DEFAULT_MAX_TARGET_LEN = 256
DEFAULT_LEARNING_RATE = 3e-4
DEFAULT_WARMUP_STEPS = 200
DEFAULT_GRAD_ACCUM = 4  # effective batch = 4 * 4 = 16


def parse_args():
    parser = argparse.ArgumentParser(description="Continue fine-tuning T5 on multi-engine log dataset.")
    parser.add_argument("--base-model", default=None,
                        help="Path to base checkpoint (default: models/oracle_log_t5_model/)")
    parser.add_argument("--train-file", default=None)
    parser.add_argument("--val-file", default=None)
    parser.add_argument("--out-dir", default=None,
                        help="Output checkpoint directory (default: models/multi_engine_t5_model/)")
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-input-len", type=int, default=DEFAULT_MAX_INPUT_LEN)
    parser.add_argument("--max-target-len", type=int, default=DEFAULT_MAX_TARGET_LEN)
    parser.add_argument("--lr", type=float, default=DEFAULT_LEARNING_RATE)
    parser.add_argument("--warmup-steps", type=int, default=DEFAULT_WARMUP_STEPS)
    parser.add_argument("--grad-accum", type=int, default=DEFAULT_GRAD_ACCUM)
    parser.add_argument("--dry-run", action="store_true",
                        help="Load a tiny subset and run 1 step to verify the pipeline works.")
    parser.add_argument("--fp16", action="store_true", default=False,
                        help="Enable FP16 training (requires CUDA GPU with fp16 support)")
    return parser.parse_args()


def resolve_paths(args):
    base_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    base_model = args.base_model or os.path.join(base_dir, "models", "oracle_log_t5_model")
    train_file = args.train_file or os.path.join(base_dir, "data", "finetune", "train_v2.jsonl")
    val_file = args.val_file or os.path.join(base_dir, "data", "finetune", "val_v2.jsonl")
    out_dir = args.out_dir or os.path.join(base_dir, "models", "multi_engine_t5_model")
    return base_model, train_file, val_file, out_dir


def load_jsonl(path, max_rows=None):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if max_rows and i >= max_rows:
                break
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    args = parse_args()
    base_model, train_file, val_file, out_dir = resolve_paths(args)

    print("=" * 60)
    print("Multi-Engine T5 Fine-Tuning")
    print("=" * 60)
    print(f"  Base model:  {base_model}")
    print(f"  Train file:  {train_file}")
    print(f"  Val file:    {val_file}")
    print(f"  Output dir:  {out_dir}")
    print(f"  Epochs:      {args.epochs}")
    print(f"  Batch size:  {args.batch_size} (grad accum: {args.grad_accum})")
    print(f"  LR:          {args.lr}")
    print(f"  Dry run:     {args.dry_run}")
    print()

    # ── Validate prerequisites ──────────────────────────────────────────────
    if not os.path.isdir(base_model):
        sys.exit(
            f"ERROR: Base model not found at {base_model}\n"
            f"The oracle_log_t5_model/ checkpoint must exist before running this script.\n"
            f"This script continues fine-tuning FROM that checkpoint, not from scratch."
        )

    for fpath in [train_file, val_file]:
        if not os.path.isfile(fpath):
            sys.exit(
                f"ERROR: Data file not found: {fpath}\n"
                f"Run this first: python -m src.data_generation.build_finetune_dataset_v2"
            )

    # ── Import heavy deps late (keep startup fast for validation) ──────────
    try:
        import torch
        from transformers import (
            AutoTokenizer,
            AutoModelForSeq2SeqLM,
            Seq2SeqTrainer,
            Seq2SeqTrainingArguments,
            DataCollatorForSeq2Seq,
            EarlyStoppingCallback,
        )
        from datasets import Dataset
    except ImportError as e:
        sys.exit(
            f"Missing dependency: {e}\n"
            f"Install with: pip install transformers datasets torch"
        )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    if device == "cpu":
        print("WARNING: Training on CPU will be very slow. Recommend using a GPU.")

    # ── Load data ───────────────────────────────────────────────────────────
    max_rows = 200 if args.dry_run else None
    print(f"\nLoading training data{' (dry-run: 200 rows)' if args.dry_run else ''}...")
    train_rows = load_jsonl(train_file, max_rows=max_rows)
    val_rows = load_jsonl(val_file, max_rows=50 if args.dry_run else None)

    # Engine distribution
    engine_counts = {}
    for r in train_rows:
        eng = r.get("engine", "oracle")
        engine_counts[eng] = engine_counts.get(eng, 0) + 1
    print(f"Train: {len(train_rows)} examples  |  Val: {len(val_rows)} examples")
    for eng, count in sorted(engine_counts.items()):
        print(f"  {eng}: {count} ({count/len(train_rows)*100:.1f}%)")

    # ── Load tokenizer and model from the Oracle checkpoint ────────────────
    print(f"\nLoading tokenizer and model from {base_model}...")
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    model = AutoModelForSeq2SeqLM.from_pretrained(base_model)
    model = model.to(device)
    print(f"Model loaded. Parameters: {sum(p.numel() for p in model.parameters()):,}")

    # ── Tokenize ────────────────────────────────────────────────────────────
    def tokenize_batch(batch):
        # Prepend instruction to the input context
        inputs = [
            f"{inst}\n\n{ctx}"
            for inst, ctx in zip(batch["instruction"], batch["input"])
        ]
        model_inputs = tokenizer(
            inputs,
            max_length=args.max_input_len,
            padding=False,  # DataCollator handles padding dynamically
            truncation=True,
        )
        targets = tokenizer(
            text_target=batch["output"],
            max_length=args.max_target_len,
            padding=False,
            truncation=True,
        )
        model_inputs["labels"] = targets["input_ids"]
        return model_inputs

    print("\nTokenizing...")
    train_ds = Dataset.from_list(train_rows).map(
        tokenize_batch, batched=True, remove_columns=train_rows[0].keys()
    )
    val_ds = Dataset.from_list(val_rows).map(
        tokenize_batch, batched=True, remove_columns=val_rows[0].keys()
    )
    print(f"Tokenized: {len(train_ds)} train / {len(val_ds)} val examples")

    # ── Data Collator (dynamic padding — lesson #2 from PROGRESS.md) ───────
    # Must use DataCollatorForSeq2Seq with padding=True, NOT padding to max_length.
    # This avoids the "all sequences must be the same length" error.
    data_collator = DataCollatorForSeq2Seq(
        tokenizer=tokenizer,
        model=model,
        padding=True,
        label_pad_token_id=-100,
    )

    # ── Training Arguments ──────────────────────────────────────────────────
    training_epochs = 1 if args.dry_run else args.epochs

    training_args = Seq2SeqTrainingArguments(
        output_dir=out_dir,
        num_train_epochs=training_epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        warmup_steps=args.warmup_steps if not args.dry_run else 0,
        weight_decay=0.01,
        predict_with_generate=True,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        fp16=args.fp16 and (device == "cuda"),
        gradient_checkpointing=True,
        logging_steps=50 if not args.dry_run else 1,
        report_to="none",
        generation_max_length=args.max_target_len,
        save_total_limit=2,
        dataloader_num_workers=0,  # avoid Windows multiprocessing issues
    )

    # ── Trainer ─────────────────────────────────────────────────────────────
    # transformers >= 4.46 uses `processing_class`, older versions use `tokenizer`.
    # We inspect the signature and pass as kwargs to avoid static type checker / linter errors
    # and prevent masking unrelated TypeErrors.
    import inspect
    sig = inspect.signature(Seq2SeqTrainer.__init__)
    trainer_kwargs = {
        "model": model,
        "args": training_args,
        "train_dataset": train_ds,
        "eval_dataset": val_ds,
        "data_collator": data_collator,
        "callbacks": [EarlyStoppingCallback(early_stopping_patience=2)] if not args.dry_run else [],
    }
    if "processing_class" in sig.parameters:
        trainer_kwargs["processing_class"] = tokenizer
    else:
        trainer_kwargs["tokenizer"] = tokenizer

    trainer = Seq2SeqTrainer(**trainer_kwargs)

    # ── Train ───────────────────────────────────────────────────────────────
    print(f"\nStarting {'DRY-RUN' if args.dry_run else 'TRAINING'} ...")
    print(f"Effective batch size: {args.batch_size * args.grad_accum}")
    trainer.train()

    if not args.dry_run:
        print(f"\nSaving best model to {out_dir}...")
        trainer.save_model(out_dir)
        tokenizer.save_pretrained(out_dir)
        print(f"Done. Model saved to {out_dir}")
        print("\nTo use this model, update src/rag/generator.py to load from:")
        print(f"  {out_dir}")
    else:
        print("\nDry run complete — pipeline is functional.")


if __name__ == "__main__":
    main()
