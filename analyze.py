"""
analyze.py - Quick Multi-Engine Log Analyzer

Automatically detects whether your log file is Oracle, PostgreSQL, or MySQL,
and generates AI diagnoses using the fine-tuned multi-engine T5 model.

Usage:
    python analyze.py path/to/logfile.log
    python analyze.py data/synthetic_logs/finetune_corpus_v2/oracle_app_01.log
    python analyze.py data/synthetic_logs/finetune_corpus_v2/postgres_app_01.log
    python analyze.py data/synthetic_logs/finetune_corpus_v2/mysql_app_01.log
"""

import sys
import os
import argparse

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath("."))

from src.rag.pipeline import analyze_log_file, save_report
from src.engine_detection import detect_engine

def main():
    parser = argparse.ArgumentParser(description="Analyze any database log file with automatic engine detection and T5 AI diagnosis.")
    parser.add_argument("log_file", nargs="?", default=None, help="Path to log file to analyze")
    parser.add_argument("--mode", default="t5", choices=["t5", "mock"], help="Generation mode (default: t5)")
    parser.add_argument("--engine", default="auto", choices=["auto", "oracle", "postgres", "mysql"], help="Force specific engine (default: auto-detect)")
    parser.add_argument("--out", default="outputs", help="Output directory for saved reports (default: outputs/)")
    args = parser.parse_args()

    # If no file provided via CLI, prompt the user interactively
    log_path = args.log_file
    if not log_path:
        print("=" * 70)
        print("  Database Log AI Analyzer (Oracle / PostgreSQL / MySQL)")
        print("=" * 70)
        log_path = input("\nEnter log file path (e.g. data/synthetic_logs/finetune_corpus_v2/oracle_app_01.log): ").strip().strip('"').strip("'")
        if not log_path:
            print("No file specified. Exiting.")
            return

    if not os.path.isfile(log_path):
        print(f"\n[ERROR] File not found: {log_path}")
        return

    # 1. Read file preview & detect engine
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    detected_engine, confidence = detect_engine(content, return_confidence=True)
    engine_to_use = detected_engine if args.engine == "auto" else args.engine

    print("\n" + "=" * 70)
    print(f"  FILE             : {os.path.abspath(log_path)}")
    print(f"  DETECTED ENGINE  : {detected_engine.upper()} (Detection Confidence: {confidence*100:.1f}%)")
    print(f"  ANALYSIS ENGINE  : {engine_to_use.upper()}")
    print(f"  AI MODEL         : models/multi_engine_t5_model (mode={args.mode})")
    print("=" * 70)
    print("Running AI analysis...")

    # 2. Run analysis
    report = analyze_log_file(
        log_path,
        mode=args.mode,
        engine=engine_to_use if args.engine != "auto" else None,
        use_classifier=True
    )

    occurrences = report.get("total_error_occurrences", 0)
    unique_codes = report.get("unique_error_codes", 0)
    real_errors = report.get("total_real_errors", 0)
    info_count = report.get("total_informational", 0)
    findings = report.get("findings", [])

    print(f"\n[Summary] Found {occurrences} error occurrences across {unique_codes} unique error code(s).")
    print(f"Classification: {real_errors} Real Error(s), {info_count} Informational Message(s)\n")

    if not findings:
        print("No errors detected in this log file.")
    else:
        for idx, f in enumerate(findings, 1):
            code = f.get("code")
            count = f.get("occurrence_count", 1)
            lines = f.get("line_numbers", [])
            clf = f.get("classification", {}).get("label", "N/A")
            exp = f.get("explanation", {})
            retrieved = f.get("retrieved_kb_codes", [])

            print("+" + "-" * 68 + "+")
            print(f"| #{idx} ERROR: {code:<18} [{clf}]   Occurrences: {count:<4} line(s): {str(lines[:5]):<10} |")
            print("+" + "-" * 68 + "+")
            print(f"  Sample Raw Line  : {f.get('example_raw_line', '')[:70]}")
            print(f"  KB Candidates    : {', '.join(retrieved) if retrieved else '(none)'}")
            print("  " + "-" * 66)
            print(f"  MEANING          :\n    {exp.get('meaning', 'N/A')}\n")
            print(f"  LIKELY CAUSE     :\n    {exp.get('likely_cause', 'N/A')}\n")
            print(f"  RECOMMENDED ACTION:\n    {exp.get('suggested_solution', 'N/A')}\n")
            print(f"  CONFIDENCE       : {exp.get('confidence', 'N/A').upper()}")
            print("+" + "-" * 68 + "+\n")

    # 3. Save report files
    paths = save_report(report, args.out)
    print("=" * 70)
    print(f"Reports saved:")
    print(f"  JSON     : {paths['json']}")
    print(f"  Markdown : {paths['markdown']}")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
