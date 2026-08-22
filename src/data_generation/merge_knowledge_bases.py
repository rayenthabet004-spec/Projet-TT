"""
merge_knowledge_bases.py

Combines per-engine KB files (Oracle, PostgreSQL, MySQL) into a single
combined_errors_kb.jsonl with an "engine" field on every entry. This combined
file is what the unified retriever, fine-tuning pipeline, and classifier use.

The Oracle KB (oracle_errors_kb.jsonl) doesn't have an "engine" field in its
existing entries, so we add "engine": "oracle" during merging. The Postgres
and MySQL KBs already have the field set by their respective builders.

Usage:
    python -m src.data_generation.merge_knowledge_bases
"""

import json
import os
import argparse


def merge_kb_files(kb_paths: dict, out_path: str):
    """Merge multiple KB JSONL files into one combined file.

    kb_paths: dict of {engine_name: file_path}
    """
    total = 0
    per_engine = {}

    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as out_f:
        for engine, path in kb_paths.items():
            if not os.path.isfile(path):
                print(f"  WARNING: {path} not found, skipping {engine}")
                continue

            count = 0
            with open(path, "r", encoding="utf-8") as in_f:
                for line in in_f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    # Ensure engine field is set
                    if "engine" not in entry:
                        entry["engine"] = engine
                    out_f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    count += 1

            per_engine[engine] = count
            total += count

    print(f"Combined KB written to {out_path}")
    print(f"  Total entries: {total}")
    for engine, count in per_engine.items():
        print(f"  {engine}: {count}")

    return out_path


def main():
    parser = argparse.ArgumentParser(description="Merge per-engine KB files into combined_errors_kb.jsonl")
    args = parser.parse_args()

    base_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    kb_dir = os.path.join(base_dir, "data", "knowledge_base")

    kb_paths = {
        "oracle": os.path.join(kb_dir, "oracle_errors_kb.jsonl"),
        "postgres": os.path.join(kb_dir, "postgres_errors_kb.jsonl"),
        "mysql": os.path.join(kb_dir, "mysql_errors_kb.jsonl"),
    }

    out_path = os.path.join(kb_dir, "combined_errors_kb.jsonl")
    merge_kb_files(kb_paths, out_path)


if __name__ == "__main__":
    main()
