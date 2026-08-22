"""
generate_finetune_logs.py

Generates a LARGE, DIVERSE corpus of synthetic Oracle alert-log-style files
covering the *entire* knowledge base (27,282 codes as of this KB), not just
the ~20 hand-templated codes in generate_synthetic_logs.py. This corpus is
the raw material build_finetune_dataset.py parses (using the project's own
log_parser.py + KB lookup) to produce fine-tuning examples -- i.e. we
literally dogfood the production pipeline to label its own training data.

WHY THIS EXISTS (vs. just using generate_synthetic_logs.py)
-------------------------------------------------------------
generate_synthetic_logs.py's MESSAGE_TEMPLATES dict only hand-covers ~20
codes with custom parameter substitution. That's fine for demoing the RAG
pipeline, but useless for fine-tuning a model across all 27k KB codes. This
script instead works generically off each KB entry's own "message" field.

PLACEHOLDER HANDLING (verified against the real KB file, not guessed)
-----------------------------------------------------------------------
Oracle's own docs render error message templates with the literal word
"string" as a placeholder (confirmed by inspecting this project's actual
oracle_errors_kb.jsonl -- e.g. "SID ' string ' contains an illegal
character", "ASM disk \" string \" is already being dropped"). We checked:
every standalone occurrence of the word "string" in a KB message is a
placeholder (9,028 of 27,282 entries), never legitimate English. The word
"number" is NOT a reliable placeholder marker though -- it shows up 1,463
times and is almost always genuine English ("Maximum number of sessions
exceeded", "Invalid number"), so we deliberately do NOT touch it.

DIVERSITY STRATEGY
-------------------
Each KB code gets OCCURRENCES_PER_CODE renderings (default 3), each with:
  - a different random placeholder substitution (so repeated occurrences of
    the same code don't look identical -- this matters for not teaching the
    model to memorize one exact string per code),
  - a randomly chosen amount of surrounding noise/context,
  - occasional multi-error context (two unrelated errors appearing close
    together, which happens in real logs and is a harder/more realistic
    case for both the parser and eventual model),
  - scattered across many output files at random positions, rather than one
    code always appearing in the same file/position.

Usage:
    python -m src.data_generation.generate_finetune_logs
    python -m src.data_generation.generate_finetune_logs --occurrences-per-code 5 --num-files 60
"""

import argparse
import json
import os
import random
import re
from datetime import datetime, timedelta

random.seed(2026)

STRING_PLACEHOLDER_RE = re.compile(r"\bstring\b")

# Generic filler pool -- doesn't need to be Oracle-domain-perfect, just
# plausible-looking enough that the parser/model see varied realistic values
# instead of the same literal word "string" every time.
FILLER_VALUES = [
    "BILLING.CUST_ORDERS", "CRM.CALL_DETAIL_RECORDS", "NETWORK_OPS.SIM_INVENTORY",
    "_SYSSMU7$", "_SYSSMU12$", "USERS", "SYSAUX", "UNDOTBS1", "DATA_TS01",
    "ttprod1", "ttprod2", "ttstandby01", "5000", "1024", "3", "17", "42",
    "/u01/app/oracle/oradata/ttprod/users01.dbf", "PK_CUSTOMER_ACCOUNTS",
    "CDR_STAGING", "INVOICE_LINES_IDX", "shared pool", "large pool",
    "APP_USER42", "session_1123", "SP2-0552", "TNS_ADMIN",
]

NOISE_LINES = [
    "Starting background process VKTM",
    "Thread 1 advanced to log sequence {n}",
    "Current log# {n} seq# {n2} mem# 0",
    "ARC0: Archival started",
    "Archived Log entry {n} added for thread 1 sequence {n2}",
    "Beginning log switch checkpoint up to RBA",
    "Completed checkpoint up to RBA",
    "Redo thread mounted read/write",
    "SUCCESS: diskgroup DATA was mounted",
    "Undo initialization finished",
    "Instance shutdown complete",
    "Autotune of undo retention is turned on.",
]


def fill_placeholders(message: str) -> str:
    """Replace every standalone 'string' placeholder with a random plausible
    value. Deliberately does NOT touch the word 'number', which is real
    English in this KB, not a placeholder (verified empirically, see
    module docstring)."""
    return STRING_PLACEHOLDER_RE.sub(lambda _: random.choice(FILLER_VALUES), message)


def _fill_noise(template: str) -> str:
    return template.format(n=random.randint(1, 999), n2=random.randint(1000, 9999))


def _oracle_timestamp(dt: datetime) -> str:
    return dt.strftime("%a %b %d %H:%M:%S %Y")


def load_kb(path):
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def render_error_block(entry, allow_followup=True):
    """Return a list of 1-2 lines representing one occurrence of this error,
    with placeholders filled in freshly (call again for a different-looking
    occurrence of the same code)."""
    code = entry["code"]
    msg = fill_placeholders(entry["message"])
    lines = [f"{code}: {msg}"]
    if allow_followup and random.random() < 0.2:
        lines.append(
            f"Errors in file /u01/app/oracle/diag/rdbms/ttprod/ttprod1/trace/"
            f"ttprod1_ora_{random.randint(10000, 99999)}.trc"
        )
    return lines


def is_informational(entry) -> bool:
    """Same heuristic used by src/classifier/build_classifier_dataset.py:
    checks BOTH cause and solution text, since ~230 of the 878 informational
    entries only carry the marker in solution (e.g. ORA-16111)."""
    cause = (entry.get("cause") or "").lower()
    solution = (entry.get("solution") or "").lower()
    return "informational" in cause or "informational" in solution


def build_occurrence_plan(kb_entries, occurrences_per_code, informational_multiplier=1):
    """Return a flat, shuffled list of (kb_entry) repeated occurrences_per_code
    times each -- this is the full set of error 'events' we need to scatter
    across the output log files.

    informational_multiplier: entries flagged informational-only (~878 of
    27,282 codes -- only 3.2% of the KB) get occurrences_per_code *
    informational_multiplier instead of just occurrences_per_code. This
    exists specifically to give the tiny classifier (src/classifier/) more
    contextual diversity for its rare negative class without changing the
    real-world class balance the KB itself reflects. Set to 1 to disable
    (original behavior, uniform occurrences for every code)."""
    plan = []
    for entry in kb_entries:
        n = occurrences_per_code * (informational_multiplier if is_informational(entry) else 1)
        for _ in range(n):
            plan.append(entry)
    random.shuffle(plan)
    return plan


def write_log_files(plan, out_dir, num_files, avg_noise_lines_between=6):
    os.makedirs(out_dir, exist_ok=True)
    # split the plan round-robin across num_files
    buckets = [[] for _ in range(num_files)]
    for i, entry in enumerate(plan):
        buckets[i % num_files].append(entry)

    for file_idx, bucket in enumerate(buckets):
        random.shuffle(bucket)
        t = datetime(2026, 7, 1, 0, 0, 0) + timedelta(days=file_idx)
        lines = [_oracle_timestamp(t)]
        i = 0
        while i < len(bucket):
            # a run of noise lines between error events
            for _ in range(random.randint(1, avg_noise_lines_between)):
                t += timedelta(seconds=random.randint(5, 120))
                lines.append(_fill_noise(random.choice(NOISE_LINES)))

            t += timedelta(seconds=random.randint(5, 120))
            entry = bucket[i]
            lines.extend(render_error_block(entry))
            i += 1

            # occasionally bundle a second, unrelated error right after --
            # realistic (cascading failures) and a harder case for the parser
            if i < len(bucket) and random.random() < 0.12:
                t += timedelta(seconds=random.randint(1, 5))
                lines.extend(render_error_block(bucket[i]))
                i += 1

        path = os.path.join(out_dir, f"finetune_corpus_{file_idx:03d}.log")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    return num_files


def main():
    parser = argparse.ArgumentParser(description="Generate a large synthetic Oracle log corpus for fine-tuning data.")
    parser.add_argument("--occurrences-per-code", type=int, default=3, help="How many varied occurrences to generate per KB code")
    parser.add_argument("--informational-multiplier", type=int, default=1, help="Extra occurrence multiplier for informational-only codes (helps the tiny classifier's rare class)")
    parser.add_argument("--num-files", type=int, default=50, help="How many output .log files to spread occurrences across")
    parser.add_argument(
        "--kb-path",
        default=os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "knowledge_base", "oracle_errors_kb.jsonl")),
    )
    parser.add_argument(
        "--out-dir",
        default=os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "synthetic_logs", "finetune_corpus")),
    )
    args = parser.parse_args()

    kb_entries = load_kb(args.kb_path)
    print(f"Loaded {len(kb_entries)} KB entries.")

    plan = build_occurrence_plan(kb_entries, args.occurrences_per_code, informational_multiplier=args.informational_multiplier)
    print(f"Planned {len(plan)} total error occurrences ({args.occurrences_per_code} per code).")

    num_files = write_log_files(plan, args.out_dir, args.num_files)
    print(f"Wrote {num_files} log files to {args.out_dir}")


if __name__ == "__main__":
    main()
