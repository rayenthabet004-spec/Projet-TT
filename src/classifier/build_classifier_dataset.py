"""
build_classifier_dataset.py

Builds the labeled dataset for the "is this actually a real error, or just
an informational message that happens to contain an ORA-style code" tiny
classifier (this is the fix for the ORA-16111 false-positive-confidence bug
documented in PROGRESS.md).

HOW LABELS ARE OBTAINED (for free, no manual annotation needed)
-------------------------------------------------------------------
The knowledge base itself already tells us which codes are purely
informational: 648 of the 27,282 scraped entries have a "cause" field that
literally says things like "This is an informational message only." (we
checked -- 156 distinct phrasings, all containing the substring
"informational", verified against the real KB file). Every occurrence of
those codes in the generated corpus is labeled 0 (not a real actionable
error); every other occurrence is labeled 1 (real error).

This reuses the SAME finetune corpus (data/synthetic_logs/finetune_corpus/)
and the SAME log_parser.py used to build the generation training set, so
you don't need to generate a second corpus just for this classifier.

Output: data/classifier/{train,val}.jsonl
Each line: {"text": "<raw_line>", "context": "<context>", "code": "...", "label": 0 or 1}

Usage:
    python -m src.classifier.build_classifier_dataset
"""

import argparse
import glob
import hashlib
import json
import os

from src.log_parser import parse_log_text

INFORMATIONAL_MARKER = "informational"


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


def is_informational(entry) -> bool:
    """An entry counts as informational if EITHER the cause or solution text
    says so. Checking cause alone misses real cases -- e.g. ORA-16111's
    cause is "This logical standby process is setting up to begin
    processing changes." (no marker), but its solution is "No action
    necessary, this informational statement is provided..." (has the
    marker). Verified against the real KB: 648 entries have the marker in
    cause, but 230 MORE entries only have it in solution -- checking cause
    alone would have silently mislabeled all 230 of those as real errors."""
    cause = (entry.get("cause") or "").lower()
    solution = (entry.get("solution") or "").lower()
    return INFORMATIONAL_MARKER in cause or INFORMATIONAL_MARKER in solution


def code_split_bucket(code: str, val_fraction: float) -> str:
    h = int(hashlib.sha256(code.encode("utf-8")).hexdigest(), 16)
    frac = (h % 10_000) / 10_000.0
    return "val" if frac < val_fraction else "train"


def extract_labeled_examples(corpus_dir, kb_by_code, context_window=2):
    examples = []
    seen_per_code = {}
    log_files = sorted(glob.glob(os.path.join(corpus_dir, "*.log")))

    for path in log_files:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        occurrences = parse_log_text(text, context_window=context_window)

        for occ in occurrences:
            entry = kb_by_code.get(occ.code)
            if entry is None:
                continue

            seen = seen_per_code.setdefault(occ.code, set())
            if occ.raw_line in seen:
                continue
            seen.add(occ.raw_line)

            label = 0 if is_informational(entry) else 1
            examples.append({
                "code": occ.code,
                "text": occ.raw_line,
                "context": occ.context,
                "label": label,
            })

    return examples, len(log_files)


def main():
    parser = argparse.ArgumentParser(description="Build the real-error-vs-informational classifier dataset.")
    parser.add_argument("--val-fraction", type=float, default=0.15)
    args = parser.parse_args()

    base_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    kb_path = os.path.join(base_dir, "data", "knowledge_base", "oracle_errors_kb.jsonl")
    corpus_dir = os.path.join(base_dir, "data", "synthetic_logs", "finetune_corpus")
    out_dir = os.path.join(base_dir, "data", "classifier")

    kb_by_code = load_kb(kb_path)
    informational_codes = {c for c, e in kb_by_code.items() if is_informational(e)}
    print(f"Loaded {len(kb_by_code)} KB entries ({len(informational_codes)} flagged informational-only).")

    if not os.path.isdir(corpus_dir) or not glob.glob(os.path.join(corpus_dir, "*.log")):
        raise SystemExit(
            f"No log files found in {corpus_dir}.\n"
            f"Run this first: python -m src.data_generation.generate_finetune_logs"
        )

    examples, num_files = extract_labeled_examples(corpus_dir, kb_by_code)
    n_pos = sum(1 for e in examples if e["label"] == 1)
    n_neg = sum(1 for e in examples if e["label"] == 0)
    print(f"Parsed {num_files} log files -> {len(examples)} labeled examples "
          f"({n_pos} real-error / {n_neg} informational-only, "
          f"{n_neg / len(examples) * 100:.1f}% negative class).")

    train, val = [], []
    for ex in examples:
        code = ex["code"]
        bucket = code_split_bucket(code, args.val_fraction)
        (val if bucket == "val" else train).append(ex)

    os.makedirs(out_dir, exist_ok=True)
    for name, rows in [("train", train), ("val", val)]:
        path = os.path.join(out_dir, f"{name}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for ex in rows:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        n_pos_split = sum(1 for e in rows if e["label"] == 1)
        n_neg_split = sum(1 for e in rows if e["label"] == 0)
        print(f"{name}: {len(rows)} examples ({n_pos_split} pos / {n_neg_split} neg) -> {path}")


if __name__ == "__main__":
    main()
