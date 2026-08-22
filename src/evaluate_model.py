"""
evaluate_model.py

Evaluates the fine-tuned multi-engine T5 model on the held-out test set
(data/finetune/test_unseen_codes_v2.jsonl — error codes never seen in training).

Metrics reported:
  1. Format adherence  — % of outputs that contain all 4 required fields
                         (MEANING / LIKELY_CAUSE / SUGGESTED_SOLUTION / CONFIDENCE)
  2. CONFIDENCE accuracy — % where predicted confidence level matches expected
  3. BLEU-4 score       — 4-gram precision vs expected output text
  4. Per-engine scores  — all metrics broken down by Oracle / Postgres / MySQL

Usage:
    python -m src.evaluate_model                     # quick: 300 examples
    python -m src.evaluate_model --n 1000            # larger sample
    python -m src.evaluate_model --all               # full 4992 test set (slow on CPU)
    python -m src.evaluate_model --model-dir models/multi_engine_t5_model
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict

REQUIRED_FIELDS = ["MEANING", "LIKELY_CAUSE", "SUGGESTED_SOLUTION", "CONFIDENCE"]
CONFIDENCE_VALUES = {"high", "medium", "low"}


# ── Simple BLEU implementation (no external deps) ─────────────────────────────
def _ngrams(tokens, n):
    return [tuple(tokens[i:i+n]) for i in range(len(tokens)-n+1)]


def bleu4(reference: str, hypothesis: str) -> float:
    ref_tokens = reference.lower().split()
    hyp_tokens = hypothesis.lower().split()
    if not hyp_tokens:
        return 0.0
    score = 1.0
    for n in range(1, 5):
        ref_ng = _ngrams(ref_tokens, n)
        hyp_ng = _ngrams(hyp_tokens, n)
        if not hyp_ng:
            return 0.0
        ref_counts = {}
        for ng in ref_ng:
            ref_counts[ng] = ref_counts.get(ng, 0) + 1
        matches = sum(min(hyp_ng.count(ng), ref_counts.get(ng, 0)) for ng in set(hyp_ng))
        precision = matches / len(hyp_ng)
        score *= precision if precision > 0 else 1e-9
    bp = min(1.0, len(hyp_tokens) / max(len(ref_tokens), 1))
    return bp * (score ** 0.25)


# ── Field parsing ─────────────────────────────────────────────────────────────
def parse_fields(text: str) -> dict:
    result = {}
    for field in REQUIRED_FIELDS:
        m = re.search(rf"{field}\s*:\s*(.+?)(?=(?:{'|'.join(REQUIRED_FIELDS)})\s*:|$)", text, re.DOTALL | re.IGNORECASE)
        if m:
            result[field] = m.group(1).strip()
    return result


def check_format(text: str) -> bool:
    parsed = parse_fields(text)
    return all(f in parsed and parsed[f] for f in REQUIRED_FIELDS)


def extract_confidence(text: str) -> str | None:
    m = re.search(r"CONFIDENCE\s*:\s*(high|medium|low)", text, re.IGNORECASE)
    return m.group(1).lower() if m else None


# ── Main evaluation ───────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Evaluate the multi-engine T5 model.")
    parser.add_argument("--model-dir", default=None,
                        help="Path to model directory (default: models/multi_engine_t5_model)")
    parser.add_argument("--test-file", default=None,
                        help="Path to test JSONL (default: data/finetune/test_unseen_codes_v2.jsonl)")
    parser.add_argument("--n", type=int, default=300,
                        help="Number of examples to evaluate (default: 300)")
    parser.add_argument("--all", action="store_true",
                        help="Evaluate on the full test set (overrides --n)")
    parser.add_argument("--batch-size", type=int, default=8,
                        help="Batch size for inference (default: 8)")
    parser.add_argument("--max-new-tokens", type=int, default=200)
    args = parser.parse_args()

    base_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    model_dir = args.model_dir or os.path.join(base_dir, "models", "multi_engine_t5_model")
    test_file = args.test_file or os.path.join(base_dir, "data", "finetune", "test_unseen_codes_v2.jsonl")

    print("=" * 62)
    print("Multi-Engine T5 Evaluation")
    print("=" * 62)
    print(f"  Model : {model_dir}")
    print(f"  Test  : {test_file}")

    if not os.path.isdir(model_dir):
        sys.exit(f"\nERROR: model not found at {model_dir}\n"
                 f"Place your Kaggle-trained model there first.")
    if not os.path.isfile(test_file):
        sys.exit(f"\nERROR: test file not found at {test_file}")

    # Load data
    with open(test_file, "r", encoding="utf-8") as f:
        all_rows = [json.loads(l) for l in f if l.strip()]

    if not args.all:
        # Stratified sample: pick evenly across engines
        by_engine = defaultdict(list)
        for r in all_rows:
            by_engine[r.get("engine", "oracle")].append(r)
        rows = []
        per_engine = args.n // max(len(by_engine), 1)
        for eng, eng_rows in sorted(by_engine.items()):
            rows.extend(eng_rows[:per_engine])
        rows = rows[:args.n]
    else:
        rows = all_rows

    print(f"  Rows  : {len(rows)} (of {len(all_rows)} total)")

    # Engine distribution in sample
    sample_engines = defaultdict(int)
    for r in rows:
        sample_engines[r.get("engine", "oracle")] += 1
    for eng, cnt in sorted(sample_engines.items()):
        print(f"    {eng}: {cnt}")
    print()

    # Load model
    try:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    except ImportError:
        sys.exit("Install torch and transformers: pip install torch transformers sentencepiece")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    print(f"Loading model...")
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_dir).to(device)
    model.eval()
    print(f"Model loaded.\n")

    # Run inference in batches
    predictions = []
    total = len(rows)

    for i in range(0, total, args.batch_size):
        batch = rows[i: i + args.batch_size]
        prompts = [f"{r['instruction']}\n\n{r['input']}" for r in batch]
        enc = tokenizer(
            prompts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        ).to(device)
        with torch.no_grad():
            out_ids = model.generate(
                **enc,
                max_new_tokens=args.max_new_tokens,
                num_beams=4,
            )
        for out_id in out_ids:
            predictions.append(tokenizer.decode(out_id, skip_special_tokens=True))

        done = min(i + args.batch_size, total)
        pct = done / total * 100
        print(f"\r  Inference: {done}/{total} ({pct:.0f}%)", end="", flush=True)

    print()

    # ── Compute metrics ───────────────────────────────────────────────────
    per_engine_stats = defaultdict(lambda: {
        "n": 0, "format_ok": 0, "conf_match": 0, "bleu_sum": 0.0,
        "missing_fields": defaultdict(int),
    })

    overall = {"n": 0, "format_ok": 0, "conf_match": 0, "bleu_sum": 0.0}

    failures = []
    for row, pred in zip(rows, predictions):
        engine = row.get("engine", "oracle")
        expected = row["output"]

        fmt_ok = check_format(pred)
        pred_conf = extract_confidence(pred)
        exp_conf  = extract_confidence(expected)
        conf_match = (pred_conf == exp_conf) if (pred_conf and exp_conf) else False
        bl = bleu4(expected, pred)

        # Missing fields
        parsed = parse_fields(pred)
        missing = []
        for field in REQUIRED_FIELDS:
            if field not in parsed or not parsed[field]:
                per_engine_stats[engine]["missing_fields"][field] += 1
                missing.append(field)

        if not fmt_ok:
            prompt = f"{row['instruction']}\n\n{row['input']}"
            in_len = len(tokenizer.encode(prompt, truncation=False))
            failures.append({
                "code": row.get("code"),
                "engine": engine,
                "input_len": in_len,
                "missing": missing,
                "pred": pred,
            })

        for stats in (overall, per_engine_stats[engine]):
            stats["n"] += 1
            stats["format_ok"] += int(fmt_ok)
            stats["conf_match"] += int(conf_match)
            stats["bleu_sum"] += bl

    # ── Print results ─────────────────────────────────────────────────────
    def print_stats(label, stats):
        n = stats["n"]
        fmt = stats["format_ok"] / n * 100 if n else 0
        conf = stats["conf_match"] / n * 100 if n else 0
        bleu = stats["bleu_sum"] / n if n else 0
        print(f"\n{'-'*62}")
        print(f"  {label}  (n={n})")
        print(f"{'-'*62}")
        print(f"  Format adherence   : {fmt:.1f}%   (all 4 fields present & non-empty)")
        print(f"  CONFIDENCE accuracy : {conf:.1f}%   (predicted level == expected level)")
        print(f"  BLEU-4             : {bleu:.4f}")
        if "missing_fields" in stats:
            missing = stats["missing_fields"]
            if missing:
                print(f"  Missing field breakdown (per {n} examples):")
                for field in REQUIRED_FIELDS:
                    m = missing.get(field, 0)
                    if m:
                        print(f"    {field}: missing in {m} ({m/n*100:.1f}%)")

    print_stats("OVERALL", overall)
    for engine in sorted(per_engine_stats.keys()):
        print_stats(engine.upper(), per_engine_stats[engine])

    if failures:
        print(f"\n{'='*62}")
        print(f"FORMAT ADHERENCE FAILING EXAMPLES DETAIL (n={len(failures)})")
        print(f"{'='*62}")
        for idx, f in enumerate(failures, 1):
            print(f"\n--- Failure #{idx} [{f['engine'].upper()} - {f['code']}] ---")
            print(f"  Input Token Length : {f['input_len']} tokens (FLAN-T5 tokenizer)")
            print(f"  Missing Fields     : {f['missing']}")
            print(f"  Raw Model Output   :\n{f['pred']}")

    print(f"\n{'='*62}")
    n = overall['n']
    fmt = overall['format_ok'] / n * 100
    conf = overall['conf_match'] / n * 100
    bleu = overall['bleu_sum'] / n
    print(f"  SUMMARY  |  Format: {fmt:.1f}%  |  Confidence: {conf:.1f}%  |  BLEU-4: {bleu:.4f}")
    print(f"{'='*62}")
    print()


if __name__ == "__main__":
    main()
