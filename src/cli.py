"""
cli.py

Command-line entry point.

Usage:
    python -m src.cli analyze path/to/log.log
    python -m src.cli analyze path/to/log.log --mode t5 --out outputs/
    python -m src.cli analyze path/to/pg_error.log --engine postgres

Engine detection:
    auto     (default) - detect Oracle/PostgreSQL/MySQL automatically
    oracle             - force Oracle log parser
    postgres           - force PostgreSQL log parser
    mysql              - force MySQL log parser

Modes:
    t5       (default) - deterministic KB lookup for confident exact matches,
                        then fine-tuned multi-engine T5 model for uncertain/unmatched errors.
    mock               - deterministic KB lookup for everything (internal/offline fallback).
"""

import argparse
import sys

from src.rag.pipeline import analyze_log_file, save_report


def main():
    parser = argparse.ArgumentParser(description="Analyze a database log file (Oracle, PostgreSQL, or MySQL) for errors, causes, and solutions.")
    parser.add_argument("command", choices=["analyze"], help="Command to run")
    parser.add_argument("log_file", help="Path to the log file to analyze")
    parser.add_argument("--mode", choices=["t5", "mock"], default="t5", help="Generation mode (default: t5)")
    parser.add_argument("--engine", choices=["auto", "oracle", "postgres", "mysql"], default="auto", help="Database engine (default: auto-detect)")
    parser.add_argument("--out", default="outputs", help="Directory to write the JSON + Markdown report to")
    parser.add_argument("--top-k", type=int, default=3, help="Number of KB entries to retrieve per error")
    parser.add_argument("--context-window", type=int, default=2, help="Lines of context to capture around each match")
    parser.add_argument("--no-classifier", action="store_true", help="Disable real-error vs informational classifier")
    parser.add_argument("--filter-informational", action="store_true", help="Exclude informational messages from final report")
    args = parser.parse_args()

    engine = None if args.engine == "auto" else args.engine
    print(f"Analyzing {args.log_file} (mode={args.mode}, engine={args.engine})...")
    report = analyze_log_file(
        args.log_file,
        mode=args.mode,
        top_k=args.top_k,
        context_window=args.context_window,
        use_classifier=not args.no_classifier,
        filter_informational=args.filter_informational,
        engine=engine,
    )

    print(f"\nFound {report['total_error_occurrences']} error occurrences across {report['unique_error_codes']} unique codes.")
    if report.get("total_real_errors") is not None:
        print(f"Classification: {report['total_real_errors']} Real Error(s), {report['total_informational']} Informational\n")
    else:
        print()

    print(f"{'CODE':<14}{'COUNT':<8}{'TYPE':<16}{'MEANING'}")
    print("-" * 96)
    for f in report["findings"]:
        clf_type = f.get("classification", {}).get("label", "N/A")
        meaning = f["explanation"]["meaning"][:55]
        print(f"{f['code']:<14}{f['occurrence_count']:<8}{clf_type:<16}{meaning}")

    paths = save_report(report, args.out)
    print(f"\nFull report saved to:\n  {paths['json']}\n  {paths['markdown']}")


if __name__ == "__main__":
    sys.exit(main())
