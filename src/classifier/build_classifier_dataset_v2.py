"""
build_classifier_dataset_v2.py

Multi-engine version of build_classifier_dataset.py. Builds the labeled
dataset for the real-error-vs-informational classifier using the combined
KB (Oracle + PostgreSQL + MySQL) and the multi-engine log corpus.

Same labeling logic as v1: entries whose cause/solution/severity says
"informational" are labeled 0, everything else is labeled 1.

Uses per-engine parsers via src.parsers dispatch.

Output: data/classifier/{train_v2, val_v2}.jsonl

Usage:
    python -m src.classifier.build_classifier_dataset_v2
"""

import argparse
import glob
import hashlib
import json
import os

from src.parsers import parse_log_text as multi_parse
from src.engine_detection import detect_engine

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
    """An entry counts as informational if the cause, solution, or severity
    text says so."""
    cause = (entry.get("cause") or "").lower()
    solution = (entry.get("solution") or "").lower()
    severity = (entry.get("severity") or "").lower()
    return (INFORMATIONAL_MARKER in cause
            or INFORMATIONAL_MARKER in solution
            or severity == INFORMATIONAL_MARKER)


def code_split_bucket(code: str, val_fraction: float) -> str:
    h = int(hashlib.sha256(code.encode("utf-8")).hexdigest(), 16)
    frac = (h % 10_000) / 10_000.0
    return "val" if frac < val_fraction else "train"


def extract_labeled_examples(corpus_dir, kb_by_code, context_window=2):
    examples = []
    seen_per_code = {}
    log_files = sorted(glob.glob(os.path.join(corpus_dir, "*.log")))

    for path in log_files:
        # Detect engine from filename
        basename = os.path.basename(path)
        if "oracle" in basename:
            engine = "oracle"
        elif "postgres" in basename:
            engine = "postgres"
        elif "mysql" in basename:
            engine = "mysql"
        else:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            engine = detect_engine(text)

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()

        occurrences = multi_parse(text, engine=engine, context_window=context_window)

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
                "engine": engine,
                "text": occ.raw_line,
                "context": occ.context,
                "label": label,
            })

    return examples, len(log_files)


def main():
    parser = argparse.ArgumentParser(description="Build the multi-engine classifier dataset.")
    parser.add_argument("--val-fraction", type=float, default=0.15)
    args = parser.parse_args()

    base_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    kb_path = os.path.join(base_dir, "data", "knowledge_base", "combined_errors_kb.jsonl")
    corpus_dir = os.path.join(base_dir, "data", "synthetic_logs", "finetune_corpus_v2")
    out_dir = os.path.join(base_dir, "data", "classifier")

    kb_by_code = load_kb(kb_path)
    informational_codes = {c for c, e in kb_by_code.items() if is_informational(e)}
    print(f"Loaded {len(kb_by_code)} KB entries ({len(informational_codes)} flagged informational-only).")

    if not os.path.isdir(corpus_dir) or not glob.glob(os.path.join(corpus_dir, "*.log")):
        raise SystemExit(
            f"No log files found in {corpus_dir}.\n"
            f"Run this first: python -m src.data_generation.generate_finetune_logs_v2"
        )

    examples, num_files = extract_labeled_examples(corpus_dir, kb_by_code)
    n_pos = sum(1 for e in examples if e["label"] == 1)
    n_neg = sum(1 for e in examples if e["label"] == 0)
    print(f"Parsed {num_files} log files -> {len(examples)} labeled examples "
          f"({n_pos} real-error / {n_neg} informational-only, "
          f"{n_neg / len(examples) * 100:.1f}% negative class).")

    # Per-engine stats
    engine_counts = {}
    for ex in examples:
        eng = ex.get("engine", "unknown")
        engine_counts[eng] = engine_counts.get(eng, 0) + 1
    for eng, count in sorted(engine_counts.items()):
        print(f"  {eng}: {count} examples")

    train, val = [], []
    for ex in examples:
        code = ex["code"]
        bucket = code_split_bucket(code, args.val_fraction)
        (val if bucket == "val" else train).append(ex)

    os.makedirs(out_dir, exist_ok=True)
    for name, rows in [("train_v2", train), ("val_v2", val)]:
        path = os.path.join(out_dir, f"{name}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for ex in rows:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        n_pos_split = sum(1 for e in rows if e["label"] == 1)
        n_neg_split = sum(1 for e in rows if e["label"] == 0)
        print(f"{name}: {len(rows)} examples ({n_pos_split} pos / {n_neg_split} neg) -> {path}")


if __name__ == "__main__":
    main()
