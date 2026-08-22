"""
interactive_test.py

Interactive playground to test the multi-engine fine-tuned T5 model on any log snippet.
Usage:
    python interactive_test.py
"""

import sys
import os

# Set working directory to project root
sys.path.insert(0, os.path.abspath("."))

from src.rag.pipeline import analyze_log
from src.rag.knowledge_base import load_default_kb
from src.rag.retriever import Retriever

def main():
    print("=" * 65)
    print("  Multi-Engine Database Log AI Diagnostic Playground")
    print("  Model: models/multi_engine_t5_model (FLAN-T5-base)")
    print("  Engines: Oracle, PostgreSQL, MySQL (Auto-detected)")
    print("=" * 65)
    print("Loading Knowledge Base and T5 Model...")
    kb = load_default_kb()
    retriever = Retriever(kb)
    print("Ready!\n")
    print("Type or paste a log line below (or 'exit' / 'quit' to stop).")
    print("-" * 65)

    samples = [
        ("Oracle", "ORA-01555: snapshot too old: rollback segment number 12 with name \"_SYSSMU12$\" too small"),
        ("PostgreSQL", "2026-08-21 12:00:00 UTC [1234] ERROR:  relation \"users_idx\" does not exist (SQLSTATE 42P01)"),
        ("MySQL", "2026-08-21T10:00:00.000000Z 12 [ERROR] [MY-001062] [Server] Duplicate entry 'admin@test.com' for key 'users.email_unique'")
    ]

    print("Quick sample presets you can try:")
    for idx, (eng, sample) in enumerate(samples, 1):
        print(f"  [{idx}] {eng}: {sample}")
    print("-" * 65)

    while True:
        try:
            user_input = input("\n[Enter log line or 1/2/3 preset] > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            print("Goodbye!")
            break

        # Check for preset shortcuts
        if user_input in ("1", "2", "3"):
            user_input = samples[int(user_input) - 1][1]
            print(f"Running sample: {user_input}")

        report = analyze_log(
            user_input,
            kb=kb,
            retriever=retriever,
            mode="t5",
            use_classifier=True
        )

        engine_detected = report.get("engine", "unknown")
        findings = report.get("findings", [])

        print("\n" + "=" * 65)
        print(f"ENGINE DETECTED : {engine_detected.upper()}")
        if not findings:
            print("No structured error code detected in the input log.")
            print("=" * 65)
            continue

        for f in findings:
            code = f.get("code")
            clf = f.get("classification", {}).get("label", "N/A")
            exp = f.get("explanation", {})
            retrieved = f.get("retrieved_kb_codes", [])

            print(f"ERROR CODE      : {code}")
            print(f"CLASSIFICATION  : {clf}")
            print(f"KB CANDIDATES   : {retrieved}")
            print("-" * 65)
            print(f"MEANING:\n  {exp.get('meaning')}\n")
            print(f"LIKELY CAUSE:\n  {exp.get('likely_cause')}\n")
            print(f"SUGGESTED SOLUTION:\n  {exp.get('suggested_solution')}\n")
            print(f"CONFIDENCE:\n  {exp.get('confidence')}")
        print("=" * 65)

if __name__ == "__main__":
    main()
