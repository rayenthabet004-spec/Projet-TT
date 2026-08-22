"""
build_finetune_dataset_v2.py

Multi-engine version of build_finetune_dataset.py. Turns the multi-engine
synthetic log corpus (data/synthetic_logs/finetune_corpus_v2/) into supervised
fine-tuning examples spanning Oracle, PostgreSQL, AND MySQL.

Key differences from v1 (build_finetune_dataset.py):
- Uses the combined KB (combined_errors_kb.jsonl)
- Per-example instruction text names the engine (lesson from BUILD_PLAN §4d):
  "Analyze this Oracle/PostgreSQL/MySQL database log entry..."
- Dispatches to the correct per-engine parser via src.parsers
- Uses the same code-level split with zero cross-split overlap (lesson #5)
- Derives target MEANING from the rendered log line, not KB template (lesson #4)

Output: data/finetune/{train_v2, val_v2, test_unseen_codes_v2}.jsonl

Usage:
    python -m src.data_generation.build_finetune_dataset_v2
"""

import argparse
import glob
import hashlib
import json
import os
import re

from src.parsers import parse_log_text as multi_parse
from src.engine_detection import detect_engine
from src.rag.knowledge_base import load_default_kb
from src.rag.retriever import Retriever

# Per-engine instruction templates (the engine name in the instruction is what
# teaches the model which vocabulary/domain to use — §4d of BUILD_PLAN)
INSTRUCTIONS = {
    "oracle": (
        "Analyze this Oracle database log entry and explain the error. "
        "Respond in the format MEANING / LIKELY_CAUSE / SUGGESTED_SOLUTION / CONFIDENCE."
    ),
    "postgres": (
        "Analyze this PostgreSQL database log entry and explain the error. "
        "Respond in the format MEANING / LIKELY_CAUSE / SUGGESTED_SOLUTION / CONFIDENCE."
    ),
    "mysql": (
        "Analyze this MySQL database log entry and explain the error. "
        "Respond in the format MEANING / LIKELY_CAUSE / SUGGESTED_SOLUTION / CONFIDENCE."
    ),
}


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


def build_output(entry, rendered_message: str, confidence: str = "high"):
    """Build the target text. Uses the rendered (placeholder-filled) message
    from the log line, not the KB template (lesson #4). Confidence is derived
    from retrieval quality (not hardcoded)."""
    return (
        f"MEANING: {rendered_message}.\n"
        f"LIKELY_CAUSE: {entry['cause']}\n"
        f"SUGGESTED_SOLUTION: {entry['solution']}\n"
        f"CONFIDENCE: {confidence}"
    )


def build_hedged_output(rendered_message: str, retrieved: list, confidence: str):
    """Build target text for low/medium confidence cases where no exact match exists."""
    if confidence == "medium" and retrieved:
        best_entry = retrieved[0][0]
        cause = f"Possible relation to {best_entry.code} ({best_entry.message}); root cause unconfirmed from logs."
        solution = f"Investigate potential relation to {best_entry.code}. Verify database logs and application state around this event."
    else:  # low confidence
        cause = "Unconfirmed error cause; no matching knowledge base signature found."
        solution = "Inspect recent database logs, active queries, and system status around the reported timestamp."

    return (
        f"MEANING: {rendered_message}.\n"
        f"LIKELY_CAUSE: {cause}\n"
        f"SUGGESTED_SOLUTION: {solution}\n"
        f"CONFIDENCE: {confidence}"
    )


def _format_retrieved_block(retrieved):
    """Format retrieved KB entries into a text block matching inference format.
    Returns (block_text, confidence_level)."""
    if not retrieved:
        return "(no relevant knowledge base entries found)", "low"

    lines = []
    best_score = retrieved[0][1] if retrieved else 0

    for entry, score in retrieved:
        lines.append(
            f"- [{entry.code}] {entry.message}\n"
            f"  cause: {entry.cause}\n"
            f"  solution: {entry.solution}\n"
            f"  (score: {score:.1f})"
        )

    block = "\n".join(lines)

    # Derive confidence from retrieval quality
    if best_score >= 999.0:  # exact code match
        confidence = "high"
    elif best_score >= 5.0:  # strong lexical match
        confidence = "medium"
    else:
        confidence = "low"

    return block, confidence


def _extract_rendered_message(code: str, raw_line: str, entry: dict, engine: str) -> str:
    """Extract the actual rendered message from the log line."""
    if engine == "oracle":
        prefix = f"{code}:"
        if raw_line.strip().startswith(prefix):
            return raw_line.strip()[len(prefix):].strip()
    elif engine == "postgres":
        # PG format: ... ERROR:  message (SQLSTATE code)
        m = re.search(r"(?:ERROR|FATAL|WARNING|PANIC):\s+(.+?)(?:\s*\(SQLSTATE\s+\w+\))?$", raw_line)
        if m:
            return m.group(1).strip()
    elif engine == "mysql":
        # MySQL format: ... [ERROR] [MY-NNNNNN] [Subsystem] message
        m = re.search(r"\[\w+\]\s+\[MY-\d+\]\s+\[\w+\]\s+(.+)$", raw_line)
        if m:
            return m.group(1).strip()

    if entry and "message" in entry:
        return entry["message"]
    return raw_line


def extract_examples_from_corpus(corpus_dir, kb_by_code, context_window=2, retriever=None, imperfect_fraction=0.08):
    """Parse logs and build training examples with retrieved KB context.

    Generates a realistic distribution of confidence levels:
    - High: exact KB code matches (~90% of occurrences)
    - Medium / Low: pseudo-codes, unmatched codes, and simulated imperfect-retrieval
      examples where exact match is withheld (~10% of occurrences).
    """
    examples = []
    seen_per_code = {}
    retrieval_cache = {}  # cache (query_prefix, excluded_code) -> (kb_block, confidence, retrieved)
    log_files = sorted(glob.glob(os.path.join(corpus_dir, "*.log")))

    for file_idx, path in enumerate(log_files, 1):
        basename = os.path.basename(path)
        if file_idx % 10 == 0 or file_idx == len(log_files):
            print(f"  [{file_idx}/{len(log_files)}] Processing {basename} ({len(examples)} examples so far)...", flush=True)

        # Detect engine from filename pattern
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
        instruction = INSTRUCTIONS.get(engine, INSTRUCTIONS["oracle"])

        for occ in occurrences:
            seen = seen_per_code.setdefault(occ.code, set())
            if occ.context in seen:
                continue
            seen.add(occ.context)

            entry = kb_by_code.get(occ.code)
            is_pseudo = getattr(occ, "is_pseudo_code", False) or occ.code.startswith("PG-")
            rendered_msg = _extract_rendered_message(occ.code, occ.raw_line, entry or {}, engine)

            # Deterministic simulation of imperfect retrieval:
            # - 90% exact match (High)
            # - ~5% lexical candidate retrieval (Medium)
            # - ~5% weak/no retrieval match (Low)
            h = int(hashlib.md5(occ.context.encode("utf-8")).hexdigest(), 16)
            mod = h % 100
            simulate_medium = (entry is not None and not is_pseudo and (0 <= mod < 5))
            simulate_low = (entry is not None and not is_pseudo and (5 <= mod < 10))

            if entry is not None and not is_pseudo and not (simulate_medium or simulate_low):
                # Case 1: Exact KB match (High Confidence)
                kb_block = (
                    f"- [{entry['code']}] {entry.get('message', '')}\n"
                    f"  cause: {entry.get('cause', '')}\n"
                    f"  solution: {entry.get('solution', '')}\n"
                    f"  (score: 999.0)"
                )
                confidence = "high"
                target_output = build_output(entry, rendered_msg, confidence="high")
            elif simulate_low:
                # Case 2: Simulated low confidence (no relevant KB entries)
                kb_block = "(no relevant knowledge base entries found)"
                confidence = "low"
                retrieved = []
                target_output = build_hedged_output(rendered_msg, retrieved, confidence)
            else:
                # Case 3: Pseudo-code, unmatched code, or simulated medium lexical match
                query = f"{occ.code} {rendered_msg}" if not is_pseudo else rendered_msg
                cache_key = (occ.code, simulate_medium, rendered_msg[:40])

                if cache_key in retrieval_cache:
                    kb_block, confidence, retrieved = retrieval_cache[cache_key]
                else:
                    if retriever is not None:
                        raw_retrieved = retriever.retrieve(query, k=4)
                        if simulate_medium:
                            raw_retrieved = [pair for pair in raw_retrieved if pair[0].code != occ.code][:3]
                        else:
                            raw_retrieved = raw_retrieved[:3]
                        kb_block, confidence = _format_retrieved_block(raw_retrieved)
                        retrieved = raw_retrieved
                    else:
                        kb_block = "(no relevant knowledge base entries found)"
                        confidence = "low"
                        retrieved = []
                    retrieval_cache[cache_key] = (kb_block, confidence, retrieved)

                target_output = build_hedged_output(rendered_msg, retrieved, confidence)

            # Build input with retrieved knowledge block (matches inference format)
            input_text = (
                f"{occ.context}\n\n"
                f"RETRIEVED KNOWLEDGE:\n"
                f"{kb_block}"
            )

            examples.append({
                "code": occ.code,
                "engine": engine,
                "instruction": instruction,
                "input": input_text,
                "output": target_output,
            })

    return examples, len(log_files)


def code_split_bucket(code: str, val_fraction: float, test_fraction: float) -> str:
    """Deterministic hash-based split (lesson #5)."""
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
    parser = argparse.ArgumentParser(description="Build multi-engine fine-tuning JSONL from the v2 log corpus.")
    parser.add_argument("--val-fraction", type=float, default=0.10)
    parser.add_argument("--test-fraction", type=float, default=0.05)
    parser.add_argument("--context-window", type=int, default=2)
    args = parser.parse_args()

    base_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    kb_path = os.path.join(base_dir, "data", "knowledge_base", "combined_errors_kb.jsonl")
    corpus_dir = os.path.join(base_dir, "data", "synthetic_logs", "finetune_corpus_v2")
    out_dir = os.path.join(base_dir, "data", "finetune")

    kb_by_code = load_kb(kb_path)
    print(f"Loaded {len(kb_by_code)} KB entries from combined KB.")

    # Initialize BM25 retriever for grounding training data
    print("Initializing BM25 retriever (this may take a moment)...")
    kb = load_default_kb()
    retriever = Retriever(kb)
    print(f"Retriever ready ({len(kb.entries)} entries indexed).")

    if not os.path.isdir(corpus_dir) or not glob.glob(os.path.join(corpus_dir, "*.log")):
        raise SystemExit(
            f"No log files found in {corpus_dir}.\n"
            f"Run this first: python -m src.data_generation.generate_finetune_logs_v2"
        )

    examples, num_files = extract_examples_from_corpus(
        corpus_dir, kb_by_code, context_window=args.context_window, retriever=retriever
    )

    # Count per engine
    engine_counts = {}
    for ex in examples:
        engine_counts[ex["engine"]] = engine_counts.get(ex["engine"], 0) + 1

    print(f"Parsed {num_files} log files -> {len(examples)} training examples "
          f"covering {len(set(e['code'] for e in examples))} unique codes.")
    for eng, count in sorted(engine_counts.items()):
        print(f"  {eng}: {count} examples")

    buckets = split_examples(examples, args.val_fraction, args.test_fraction)

    write_jsonl(os.path.join(out_dir, "train_v2.jsonl"), buckets["train"])
    write_jsonl(os.path.join(out_dir, "val_v2.jsonl"), buckets["val"])
    write_jsonl(os.path.join(out_dir, "test_unseen_codes_v2.jsonl"), buckets["test"])

    train_codes = set(e["code"] for e in buckets["train"])
    val_codes = set(e["code"] for e in buckets["val"])
    test_codes = set(e["code"] for e in buckets["test"])

    print(f"\nTrain: {len(buckets['train'])} examples, {len(train_codes)} unique codes")
    print(f"Val:   {len(buckets['val'])} examples, {len(val_codes)} unique codes")
    print(f"Test:  {len(buckets['test'])} examples, {len(test_codes)} unique codes (held out)")
    print(f"\nCode overlap check (should all be 0):")
    print(f"  train & val:  {len(train_codes & val_codes)}")
    print(f"  train & test: {len(train_codes & test_codes)}")
    print(f"  val & test:   {len(val_codes & test_codes)}")
    print(f"\nWritten to {out_dir}/{{train_v2,val_v2,test_unseen_codes_v2}}.jsonl")


if __name__ == "__main__":
    main()
