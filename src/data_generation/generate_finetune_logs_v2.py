"""
generate_finetune_logs_v2.py

Multi-engine version of generate_finetune_logs.py — generates synthetic log
corpora for Oracle, PostgreSQL, AND MySQL, with realistic per-engine log
formatting. This is the raw material build_finetune_dataset_v2.py parses
to produce combined fine-tuning examples.

Each engine gets its own realistic log line format:
- Oracle: "ORA-01555: snapshot too old ..." (existing format)
- PostgreSQL: "2026-08-20 14:23:11.456 UTC [12345] ERROR:  message (SQLSTATE XXXXX)"
- MySQL: "2026-08-20T14:23:11.456789Z 0 [ERROR] [MY-NNNNNN] [Server] message"

Uses the combined KB (combined_errors_kb.jsonl) and routes each entry to
the correct engine-specific formatter.

Usage:
    python -m src.data_generation.generate_finetune_logs_v2
    python -m src.data_generation.generate_finetune_logs_v2 --occurrences-per-code 3 --num-files 50
"""

import argparse
import json
import os
import random
import re
from datetime import datetime, timedelta

random.seed(2026)

STRING_PLACEHOLDER_RE = re.compile(r"\bstring\b")

FILLER_VALUES = [
    "BILLING.CUST_ORDERS", "CRM.CALL_DETAIL_RECORDS", "NETWORK_OPS.SIM_INVENTORY",
    "_SYSSMU7$", "_SYSSMU12$", "USERS", "SYSAUX", "UNDOTBS1", "DATA_TS01",
    "ttprod1", "ttprod2", "ttstandby01", "5000", "1024", "3", "17", "42",
    "/u01/app/oracle/oradata/ttprod/users01.dbf", "PK_CUSTOMER_ACCOUNTS",
    "CDR_STAGING", "INVOICE_LINES_IDX", "shared pool", "large pool",
    "APP_USER42", "session_1123", "SP2-0552", "TNS_ADMIN",
    "app_db", "reporting_schema", "user_sessions", "pg_toast_12345",
    "idx_users_email", "pk_orders", "fk_order_customer",
]

# ── Per-engine noise lines ──

ORACLE_NOISE = [
    "Starting background process VKTM",
    "Thread 1 advanced to log sequence {n}",
    "Current log# {n} seq# {n2} mem# 0",
    "ARC0: Archival started",
    "Archived Log entry {n} added for thread 1 sequence {n2}",
    "Beginning log switch checkpoint up to RBA",
    "Completed checkpoint up to RBA",
    "Undo initialization finished",
]

PG_NOISE = [
    "LOG:  database system is ready to accept connections",
    "LOG:  autovacuum launcher started",
    "LOG:  checkpoint starting: time",
    "LOG:  checkpoint complete: wrote {n} buffers ({n2}%)",
    "LOG:  automatic vacuum of table \"app_db.public.user_sessions\": removed {n} row versions",
    "LOG:  received fast shutdown request",
    "LOG:  database system is shut down",
    "LOG:  connection authorized: user=app_user database=app_db",
]

MYSQL_NOISE = [
    "[Note] [MY-010747] [Server] Plugin 'FEDERATED' is disabled.",
    "[System] [MY-010116] [Server] /usr/sbin/mysqld (mysqld 8.0) starting as process {n}",
    "[System] [MY-013576] [InnoDB] InnoDB initialization has started.",
    "[System] [MY-013577] [InnoDB] InnoDB initialization has ended.",
    "[Note] [MY-010051] [Server] Event Scheduler: scheduler thread started",
    "[System] [MY-010931] [Server] Ready for connections. Version: '8.0' socket: '/var/run/mysqld/mysqld.sock'",
    "[Note] [MY-011240] [Server] Plugin mysqlx reported: 'X Plugin ready for connections.'",
]


def fill_placeholders(message: str) -> str:
    """Replace standalone 'string' placeholders with random values."""
    return STRING_PLACEHOLDER_RE.sub(lambda _: random.choice(FILLER_VALUES), message)


def _fill_noise(template: str) -> str:
    return template.format(n=random.randint(1, 999), n2=random.randint(1000, 9999))


def is_informational(entry) -> bool:
    """Same heuristic as the classifier dataset builder."""
    cause = (entry.get("cause") or "").lower()
    solution = (entry.get("solution") or "").lower()
    severity = (entry.get("severity") or "").lower()
    return "informational" in cause or "informational" in solution or severity == "informational"


# ── Per-engine log line formatters ──

def render_oracle_line(entry):
    """Oracle alert log format: CODE: message"""
    msg = fill_placeholders(entry["message"])
    code = entry["code"]
    lines = [f"{code}: {msg}"]
    if random.random() < 0.2:
        lines.append(
            f"Errors in file /u01/app/oracle/diag/rdbms/ttprod/ttprod1/trace/"
            f"ttprod1_ora_{random.randint(10000, 99999)}.trc"
        )
    return lines


def render_postgres_line(entry, ts: datetime):
    """PostgreSQL log format: timestamp [pid] LEVEL: message (SQLSTATE code)"""
    msg = fill_placeholders(entry["message"])
    code = entry["code"]
    pid = random.randint(1000, 65535)
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S.") + f"{random.randint(0, 999):03d} UTC"

    # Determine log level based on severity
    severity = entry.get("severity", "medium")
    if severity in ("critical", "high"):
        level = random.choice(["ERROR", "FATAL"])
    elif severity == "informational":
        level = "WARNING"
    else:
        level = "ERROR"

    main_line = f"{ts_str} [{pid}] {level}:  {msg} (SQLSTATE {code})"
    lines = [main_line]

    # Occasionally add DETAIL/HINT continuation lines
    if random.random() < 0.3:
        detail_ts = ts + timedelta(milliseconds=1)
        detail_ts_str = detail_ts.strftime("%Y-%m-%d %H:%M:%S.") + f"{random.randint(0, 999):03d} UTC"
        cause = entry.get("cause", "")
        if cause and len(cause) > 20:
            hint = cause[:120]
            lines.append(f"{detail_ts_str} [{pid}] DETAIL:  {hint}")

    return lines


def render_mysql_line(entry, ts: datetime):
    """MySQL 8+ structured format: timestamp thread [level] [MY-code] [subsystem] message"""
    msg = fill_placeholders(entry["message"])
    code = entry["code"]  # Already in MY-NNNNNN format
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{random.randint(0, 999999):06d}Z"

    severity = entry.get("severity", "medium")
    if severity == "informational":
        level = random.choice(["Warning", "Note"])
    else:
        level = "ERROR"

    # Pick a subsystem based on keywords
    keywords = " ".join(entry.get("keywords", []))
    if "innodb" in keywords.lower():
        subsystem = "InnoDB"
    elif "replication" in keywords.lower() or "binlog" in keywords.lower():
        subsystem = "Repl"
    else:
        subsystem = "Server"

    main_line = f"{ts_str} 0 [{level}] [{code}] [{subsystem}] {msg}"
    return [main_line]


def load_kb(path):
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def build_occurrence_plan(kb_entries, occurrences_per_code, informational_multiplier=1):
    """Return a shuffled list of (entry, engine) tuples."""
    plan = []
    for entry in kb_entries:
        engine = entry.get("engine", "oracle")
        n = occurrences_per_code * (informational_multiplier if is_informational(entry) else 1)
        for _ in range(n):
            plan.append((entry, engine))
    random.shuffle(plan)
    return plan


def write_log_files(plan, out_dir, num_files, avg_noise_between=5):
    os.makedirs(out_dir, exist_ok=True)

    # Split plan by engine, then distribute within engine
    by_engine = {"oracle": [], "postgres": [], "mysql": []}
    for entry, engine in plan:
        by_engine.setdefault(engine, []).append(entry)

    total_files = 0
    for engine, entries in by_engine.items():
        if not entries:
            continue

        # Allocate files proportionally
        engine_files = max(1, int(num_files * len(entries) / len(plan)))
        buckets = [[] for _ in range(engine_files)]
        for i, entry in enumerate(entries):
            buckets[i % engine_files].append(entry)

        noise_pool = {"oracle": ORACLE_NOISE, "postgres": PG_NOISE, "mysql": MYSQL_NOISE}[engine]

        for file_idx, bucket in enumerate(buckets):
            random.shuffle(bucket)
            t = datetime(2026, 7, 1, 0, 0, 0) + timedelta(days=file_idx, hours=random.randint(0, 23))

            lines = []
            # Engine-specific header
            if engine == "oracle":
                lines.append(t.strftime("%a %b %d %H:%M:%S %Y"))
            elif engine == "postgres":
                lines.append(f"LOG:  database system was shut down at {t.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            else:
                lines.append(f"{t.strftime('%Y-%m-%dT%H:%M:%S.000000Z')} 0 [System] [MY-010116] [Server] mysqld starting")

            for entry in bucket:
                # Add noise
                for _ in range(random.randint(1, avg_noise_between)):
                    t += timedelta(seconds=random.randint(5, 120))
                    if engine == "oracle":
                        lines.append(_fill_noise(random.choice(noise_pool)))
                    elif engine == "postgres":
                        ts_str = t.strftime("%Y-%m-%d %H:%M:%S.") + f"{random.randint(0, 999):03d} UTC"
                        lines.append(f"{ts_str} [{random.randint(1000, 65535)}] {_fill_noise(random.choice(noise_pool))}")
                    else:
                        ts_str = t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{random.randint(0, 999999):06d}Z"
                        lines.append(f"{ts_str} 0 {_fill_noise(random.choice(noise_pool))}")

                t += timedelta(seconds=random.randint(5, 120))
                if engine == "oracle":
                    lines.extend(render_oracle_line(entry))
                elif engine == "postgres":
                    lines.extend(render_postgres_line(entry, t))
                else:
                    lines.extend(render_mysql_line(entry, t))

            fname = f"finetune_{engine}_{file_idx:03d}.log"
            path = os.path.join(out_dir, fname)
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

            total_files += 1

    return total_files


def main():
    parser = argparse.ArgumentParser(description="Generate multi-engine synthetic log corpus for fine-tuning.")
    parser.add_argument("--occurrences-per-code", type=int, default=3)
    parser.add_argument("--informational-multiplier", type=int, default=8)
    parser.add_argument("--num-files", type=int, default=60)
    parser.add_argument(
        "--kb-path",
        default=os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "knowledge_base", "combined_errors_kb.jsonl")),
    )
    parser.add_argument(
        "--out-dir",
        default=os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "synthetic_logs", "finetune_corpus_v2")),
    )
    args = parser.parse_args()

    kb_entries = load_kb(args.kb_path)
    print(f"Loaded {len(kb_entries)} KB entries from combined KB.")

    engines = {}
    for e in kb_entries:
        eng = e.get("engine", "oracle")
        engines[eng] = engines.get(eng, 0) + 1
    for eng, count in sorted(engines.items()):
        print(f"  {eng}: {count} entries")

    plan = build_occurrence_plan(kb_entries, args.occurrences_per_code, args.informational_multiplier)
    print(f"Planned {len(plan)} total error occurrences.")

    num_files = write_log_files(plan, args.out_dir, args.num_files)
    print(f"Wrote {num_files} log files to {args.out_dir}")


if __name__ == "__main__":
    main()
