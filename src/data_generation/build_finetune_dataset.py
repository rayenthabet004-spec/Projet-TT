"""
build_finetune_dataset.py  (v2)

Turns the synthetic log corpus (data/synthetic_logs/finetune_corpus/*.log,
produced by generate_finetune_logs.py) into supervised fine-tuning examples,
using the project's OWN log_parser.py + knowledge base lookup as the
labeling function. This is deliberate: it means every training example is
generated exactly the way the production pipeline would encounter it (same
regex extraction, same context window, same code normalization), rather than
being hand-templated separately and risking drift from the real pipeline.

THIS REPLACES v1 of this file (kept alongside as build_finetune_dataset_v1_backup.py
for reference), which only worked off the 58 hand-written KB entries via
hardcoded MESSAGE_TEMPLATES. Key differences:
  - Works across the full KB (27,282 entries as of this build), not just 58.
  - Reads real generated .log files through log_parser, instead of building
    (input, output) pairs directly from templates.
  - Splits by ERROR CODE, not by row (see "why code-level split" below) --
    v1 used a per-code *stratified* split, which put examples of the SAME
    code in both train and val. That's fine for maximizing coverage, but it
    means val performance doesn't actually tell you how well the model
    generalizes to a code it never saw during training. This version
    produces THREE files:
      train.jsonl / val.jsonl  -- codes split so every code is fully in one
                                  side or the other (see split logic), for a
                                  realistic training signal
      test_unseen_codes.jsonl  -- a held-out set of ENTIRE codes never
                                  touched during training at all, specifically
                                  to measure true generalization

Output schema per line (same instruction/input/output shape as v1, so it's
still a drop-in fit for the Qwen2.5 LoRA/QLoRA notebook):
    {"code": "ORA-01555", "instruction": "...", "input": "...", "output": "..."}

For the T5/BART seq2seq notebook, source text = instruction + "\n\n" + input,
target text = output (concatenation done in the notebook, not stored twice
here, to keep the file smaller -- KB is already ~9MB, no need to duplicate).

Usage:
    python -m src.data_generation.build_finetune_dataset
    python -m src.data_generation.build_finetune_dataset --val-fraction 0.1 --test-fraction 0.05
"""

import argparse
import glob
import hashlib
import json
import os

from src.log_parser import parse_log_text

INSTRUCTION = (
    "Analyze this Oracle database log entry and explain the error. "
    "Respond in the format MEANING / LIKELY_CAUSE / SUGGESTED_SOLUTION / CONFIDENCE."
)


def load_kb(path):
    by_code = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            by_code[d["code"]] = d
    return by_code


def build_output(entry, rendered_message: str):
    """rendered_message is the actual message text as it appeared in the log
    line (placeholders already filled in by generate_finetune_logs.py), NOT
    entry['message'] directly -- the KB's raw message field still contains
    literal 'string' placeholder tokens for ~9,000 entries, and using it
    verbatim would train the model to output unfilled placeholders even
    though the input it's conditioned on shows real filled-in values. Using
    the rendered text keeps input/output consistent (and is arguably a more
    grounded MEANING statement anyway, since it echoes what was actually
    seen)."""
    return (
        f"MEANING: {rendered_message}.\n"
        f"LIKELY_CAUSE: {entry['cause']}\n"
        f"SUGGESTED_SOLUTION: {entry['solution']}\n"
        f"CONFIDENCE: high"
    )


def extract_examples_from_corpus(corpus_dir, kb_by_code, context_window=2):
    """Parse every .log file in corpus_dir and turn each matched occurrence
    into a training example, using the KB entry for its code as ground
    truth. Occurrences whose code isn't in the KB are skipped (shouldn't
    happen if the corpus was generated from this same KB, but real logs
    later will have this case -- it's just not a training example)."""
    examples = []
    seen_per_code = {}  # code -> set of input strings already used, to skip near-duplicates
    log_files = sorted(glob.glob(os.path.join(corpus_dir, "*.log")))

    for path in log_files:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        occurrences = parse_log_text(text, context_window=context_window)

        for occ in occurrences:
            entry = kb_by_code.get(occ.code)
            if entry is None:
                continue  # code not in KB -- can't produce a ground-truth target

            seen = seen_per_code.setdefault(occ.code, set())
            if occ.context in seen:
                continue  # skip near-identical repeats of the same code
            seen.add(occ.context)

            rendered_message = entry["message"]
            prefix = f"{occ.code}:"
            if occ.raw_line.startswith(prefix):
                rendered_message = occ.raw_line[len(prefix):].strip()

            examples.append({
                "code": occ.code,
                "instruction": INSTRUCTION,
                "input": occ.context,
                "output": build_output(entry, rendered_message),
            })

    return examples, len(log_files)


def code_split_bucket(code: str, val_fraction: float, test_fraction: float) -> str:
    """Deterministic split assignment based on a hash of the code string, so
    re-running this script always produces the same split (reproducible),
    and every occurrence of a given code lands in exactly the same bucket
    (no leakage of a code's phrasing across train/val/test)."""
    h = int(hashlib.sha256(code.encode("utf-8")).hexdigest(), 16)
    frac = (h % 10_000) / 10_000.0
    if frac < test_fraction:
        return "test"
    if frac < test_fraction + val_fraction:
        return "val"
    return "train"


def split_examples(examples, val_fraction, test_fraction):
    buckets = {"train": [], "val": [], "test": []}
    for ex in examples:
        bucket = code_split_bucket(ex["code"], val_fraction, test_fraction)
        buckets[bucket].append(ex)
    return buckets


def write_jsonl(path, examples):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Build fine-tuning JSONL from the generated log corpus.")
    parser.add_argument("--val-fraction", type=float, default=0.10)
    parser.add_argument("--test-fraction", type=float, default=0.05)
    parser.add_argument("--context-window", type=int, default=2)
    args = parser.parse_args()

    base_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    kb_path = os.path.join(base_dir, "data", "knowledge_base", "oracle_errors_kb.jsonl")
    corpus_dir = os.path.join(base_dir, "data", "synthetic_logs", "finetune_corpus")
    out_dir = os.path.join(base_dir, "data", "finetune")

    kb_by_code = load_kb(kb_path)
    print(f"Loaded {len(kb_by_code)} KB entries.")

    if not os.path.isdir(corpus_dir) or not glob.glob(os.path.join(corpus_dir, "*.log")):
        raise SystemExit(
            f"No log files found in {corpus_dir}.\n"
            f"Run this first: python -m src.data_generation.generate_finetune_logs"
        )

    examples, num_files = extract_examples_from_corpus(corpus_dir, kb_by_code, context_window=args.context_window)
    print(f"Parsed {num_files} log files -> {len(examples)} training examples "
          f"covering {len(set(e['code'] for e in examples))} unique codes.")

    buckets = split_examples(examples, args.val_fraction, args.test_fraction)

    write_jsonl(os.path.join(out_dir, "train.jsonl"), buckets["train"])
    write_jsonl(os.path.join(out_dir, "val.jsonl"), buckets["val"])
    write_jsonl(os.path.join(out_dir, "test_unseen_codes.jsonl"), buckets["test"])

    train_codes = set(e["code"] for e in buckets["train"])
    val_codes = set(e["code"] for e in buckets["val"])
    test_codes = set(e["code"] for e in buckets["test"])

    print(f"\nTrain: {len(buckets['train'])} examples, {len(train_codes)} unique codes")
    print(f"Val:   {len(buckets['val'])} examples, {len(val_codes)} unique codes")
    print(f"Test:  {len(buckets['test'])} examples, {len(test_codes)} unique codes (held out entirely -- true generalization check)")
    print(f"\nCode overlap sanity check (should all be 0):")
    print(f"  train & val:  {len(train_codes & val_codes)}")
    print(f"  train & test: {len(train_codes & test_codes)}")
    print(f"  val & test:   {len(val_codes & test_codes)}")
    print(f"\nWritten to {out_dir}/{{train,val,test_unseen_codes}}.jsonl")


if __name__ == "__main__":
    main()
