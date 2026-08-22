"""
generate_synthetic_logs.py

Generates synthetic Oracle alert-log-style files. Since we don't have real
Tunisie Telecom logs, this creates realistic-*looking* logs by:
  1. Mixing in normal/benign Oracle alert log noise (checkpoints, archiving,
     startup messages) -- like a real alert log, most lines are NOT errors.
  2. Injecting real Oracle error codes (pulled from our knowledge base) at
     random points, with plausible-looking arguments (segment names,
     tablespace names, session IDs, etc.) substituted into message templates.
  3. Producing timestamps in Oracle's native alert-log format.

This is templated/generated content -- not a copy of any real system's logs.

Usage:
    python src/data_generation/generate_synthetic_logs.py
"""

import json
import os
import random
from datetime import datetime, timedelta

random.seed(42)

TABLESPACES = ["USERS", "SYSTEM", "SYSAUX", "TEMP", "UNDOTBS1", "DATA_TS01", "IDX_TS01", "ARCHIVE_TS"]
SEGMENT_NAMES = ["_SYSSMU3$", "_SYSSMU7$", "_SYSSMU12$", "CUST_ORDERS_IDX", "BILLING_FACT", "CDR_STAGING"]
SCHEMAS = ["BILLING", "CRM", "NETWORK_OPS", "CDR_APP", "REPORTING"]
OBJECTS = ["CUSTOMER_ACCOUNTS", "CALL_DETAIL_RECORDS", "INVOICE_LINES", "SIM_INVENTORY", "NETWORK_ALARMS"]
HOSTS = ["ttdb-prod01", "ttdb-prod02", "ttdb-standby01"]

# Message templates keyed by error code -- lightweight parameter substitution
# to make each occurrence look slightly different, like a real system would.
MESSAGE_TEMPLATES = {
    "ORA-00001": 'ORA-00001: unique constraint ({schema}.PK_{obj}) violated',
    "ORA-01555": 'ORA-01555: snapshot too old: rollback segment number {n} with name "{seg}" too small',
    "ORA-01652": 'ORA-01652: unable to extend temp segment by {n} in tablespace {ts}',
    "ORA-01654": 'ORA-01654: unable to extend index {schema}.{obj}_IDX by {n} in tablespace {ts}',
    "ORA-01658": 'ORA-01658: unable to create INITIAL extent for segment in tablespace {ts}',
    "ORA-00257": "ORA-00257: archiver error. Connect internal only, until freed.",
    "ORA-00060": "ORA-00060: deadlock detected while waiting for resource",
    "ORA-04031": 'ORA-04031: unable to allocate {n}KB of shared memory ("shared pool","{obj}","SQLA","kglseshtx")',
    "ORA-01000": "ORA-01000: maximum open cursors exceeded",
    "ORA-00018": "ORA-00018: maximum number of sessions exceeded",
    "TNS-12154": "TNS-12154: TNS:could not resolve the connect identifier specified",
    "TNS-12514": 'TNS-12514: TNS:listener does not currently know of service requested in connect descriptor',
    "TNS-12541": "TNS-12541: TNS:no listener",
    "ORA-03113": "ORA-03113: end-of-file on communication channel",
    "ORA-28000": 'ORA-28000: the account is locked',
    "ORA-01017": "ORA-01017: invalid username/password; logon denied",
    "ORA-00600": 'ORA-00600: internal error code, arguments: [{n}], [kcbz_check_objd_typ], [], [], [], [], [], []',
    "ORA-00942": "ORA-00942: table or view does not exist",
    "ORA-06502": 'ORA-06502: PL/SQL: numeric or value error: character string buffer too small',
    "ORA-16038": "ORA-16038: log {n} sequence# {n2} cannot be archived",
}

NOISE_LINES = [
    "Starting background process VKTM",
    "VKTM started with pid={pid}",
    "Thread 1 advanced to log sequence {n}",
    "Current log# {n} seq# {n2} mem# 0",
    "ARC0: Archival started",
    "ARC1: Archival started",
    "Archived Log entry {n} added for thread 1 sequence {n2}",
    "Beginning log switch checkpoint up to RBA",
    "Completed checkpoint up to RBA",
    "Redo thread mounted read/write",
    "SUCCESS: diskgroup DATA was mounted",
    "Shared IO Pool defaulting to {n}M",
    "Adaptive Thread Scheduling monitor started",
    "Instance shutdown complete",
    "Database Characterset is AL32UTF8",
    "Autotune of undo retention is turned on.",
    "LOGSTDBY status: ORA-16111: log mining and apply setting up",
    "Undo initialization finished",
    "Buffer Cache Full Scan Watermark set",
]


def _fill(template: str) -> str:
    return template.format(
        n=random.randint(1, 999),
        n2=random.randint(1000, 9999),
        pid=random.randint(1000, 9999),
        schema=random.choice(SCHEMAS),
        obj=random.choice(OBJECTS),
        seg=random.choice(SEGMENT_NAMES),
        ts=random.choice(TABLESPACES),
    )


def _oracle_timestamp(dt: datetime) -> str:
    # e.g. "Sun Jul 05 14:23:11 2026"
    return dt.strftime("%a %b %d %H:%M:%S %Y")


def generate_log(num_lines=400, error_rate=0.06, start_time=None, error_codes=None):
    """Generate one synthetic alert-log-style file as a list of lines."""
    if start_time is None:
        start_time = datetime(2026, 7, 1, 0, 0, 0)
    if error_codes is None:
        error_codes = list(MESSAGE_TEMPLATES.keys())

    lines = []
    t = start_time
    for _ in range(num_lines):
        t += timedelta(seconds=random.randint(5, 240))
        if random.random() < 0.15:
            lines.append("")  # blank separator lines, like real alert logs
            lines.append(_oracle_timestamp(t))

        if random.random() < error_rate:
            code = random.choice(error_codes)
            lines.append(_fill(MESSAGE_TEMPLATES[code]))
            # some errors have a natural one-line follow-up in real logs
            if code == "ORA-01652":
                lines.append(f"ORA-1652 signalled during: INSERT INTO {random.choice(SCHEMAS)}.{random.choice(OBJECTS)}...")
            if code == "ORA-00600":
                lines.append(f"Errors in file /u01/app/oracle/diag/rdbms/ttprod/ttprod1/trace/ttprod1_ora_{random.randint(10000,99999)}.trc")
        else:
            lines.append(_fill(random.choice(NOISE_LINES)))

    return lines


def write_log_file(path, num_lines=400, error_rate=0.06, start_time=None):
    lines = generate_log(num_lines=num_lines, error_rate=error_rate, start_time=start_time)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def main():
    out_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "synthetic_logs"))
    os.makedirs(out_dir, exist_ok=True)

    write_log_file(
        os.path.join(out_dir, "alert_ttprod1_2026-07-01.log"),
        num_lines=500,
        error_rate=0.05,
        start_time=datetime(2026, 7, 1, 0, 0, 0),
    )
    write_log_file(
        os.path.join(out_dir, "alert_ttprod1_2026-07-02.log"),
        num_lines=350,
        error_rate=0.08,
        start_time=datetime(2026, 7, 2, 0, 0, 0),
    )
    print(f"Synthetic logs written to {out_dir}")


if __name__ == "__main__":
    main()
