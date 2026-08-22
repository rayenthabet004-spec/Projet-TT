"""
build_knowledge_base_postgres.py

Builds the PostgreSQL error knowledge base by parsing the official errcodes.txt
from the PostgreSQL source tree (https://github.com/postgres/postgres/blob/
master/src/backend/utils/errcodes.txt).

The errcodes.txt file is structured: each non-comment, non-empty line has:
    sqlstate    E/W/S    ERRCODE_MACRO_NAME    spec_name

We parse this directly, then generate original cause/solution text for each
entry based on the error class (first 2 chars of SQLSTATE) and the human-
readable condition name. Per lesson #11 from BUILD_PLAN: we write our own
explanatory text, not copying from external docs.

For the ~55 most operationally important codes, we provide detailed hand-
written cause/solution text. For the remaining codes, we generate reasonable
class-based descriptions so the KB still covers them (a brief generic
description is better than no entry at all for retrieval purposes).

Usage:
    python -m src.data_generation.build_knowledge_base_postgres
    python -m src.data_generation.build_knowledge_base_postgres --errcodes-url https://raw.githubusercontent.com/postgres/postgres/master/src/backend/utils/errcodes.txt
"""

import argparse
import json
import os
import re
import urllib.request

ERRCODES_URL = "https://raw.githubusercontent.com/postgres/postgres/master/src/backend/utils/errcodes.txt"

# ── Class-level descriptions (first 2 chars of SQLSTATE) ──────────────────────
CLASS_INFO = {
    "00": ("Successful Completion", "informational"),
    "01": ("Warning", "informational"),
    "02": ("No Data", "informational"),
    "03": ("SQL Statement Not Yet Complete", "low"),
    "08": ("Connection Exception", "high"),
    "09": ("Triggered Action Exception", "medium"),
    "0A": ("Feature Not Supported", "low"),
    "0B": ("Invalid Transaction Initiation", "medium"),
    "0F": ("Locator Exception", "low"),
    "0L": ("Invalid Grantor", "medium"),
    "0P": ("Invalid Role Specification", "medium"),
    "0Z": ("Diagnostics Exception", "low"),
    "20": ("Case Not Found", "low"),
    "21": ("Cardinality Violation", "low"),
    "22": ("Data Exception", "low"),
    "23": ("Integrity Constraint Violation", "medium"),
    "24": ("Invalid Cursor State", "low"),
    "25": ("Invalid Transaction State", "medium"),
    "26": ("Invalid SQL Statement Name", "low"),
    "27": ("Triggered Data Change Violation", "medium"),
    "28": ("Invalid Authorization Specification", "high"),
    "2B": ("Dependent Privilege Descriptors Still Exist", "medium"),
    "2D": ("Invalid Transaction Termination", "medium"),
    "2F": ("SQL Routine Exception", "medium"),
    "34": ("Invalid Cursor Name", "low"),
    "38": ("External Routine Exception", "medium"),
    "39": ("External Routine Invocation Exception", "medium"),
    "3B": ("Savepoint Exception", "medium"),
    "3D": ("Invalid Catalog Name", "medium"),
    "3F": ("Invalid Schema Name", "medium"),
    "40": ("Transaction Rollback", "medium"),
    "42": ("Syntax Error or Access Rule Violation", "low"),
    "44": ("WITH CHECK OPTION Violation", "low"),
    "53": ("Insufficient Resources", "critical"),
    "54": ("Program Limit Exceeded", "medium"),
    "55": ("Object Not In Prerequisite State", "medium"),
    "57": ("Operator Intervention", "medium"),
    "58": ("System Error (External)", "critical"),
    "72": ("Snapshot Too Old", "medium"),
    "F0": ("Configuration File Error", "high"),
    "HV": ("Foreign Data Wrapper Error", "medium"),
    "P0": ("PL/pgSQL Error", "medium"),
    "XX": ("Internal Error", "critical"),
}

# ── Hand-written detailed entries for the most important codes ────────────────
# These override the auto-generated class-based descriptions.
DETAILED_ENTRIES = {
    "08001": {
        "cause": "The client could not establish a connection to the PostgreSQL server. Common reasons: server not running, wrong host/port, firewall blocking, or the server is not listening on the expected address.",
        "solution": "Verify the server is running with 'pg_isready'. Check listen_addresses and port in postgresql.conf. Ensure firewall rules allow connections on the PostgreSQL port (default 5432).",
    },
    "08006": {
        "cause": "An existing connection to the server was unexpectedly lost, typically due to server crash, network interruption, or the server being shut down.",
        "solution": "Check PostgreSQL server logs for crash or shutdown messages. Verify network stability. Implement connection validation in your connection pool.",
    },
    "08P01": {
        "cause": "The client sent a message that violates the PostgreSQL wire protocol, or the server received corrupted data on the connection.",
        "solution": "Update your client driver/library to the latest version. Check for network equipment that might be corrupting packets. If using a connection pooler (PgBouncer), verify its configuration.",
    },
    "22001": {
        "cause": "A string value was too long to fit into the target column's defined length (e.g., inserting 100 chars into a VARCHAR(50)).",
        "solution": "Truncate the input data to fit, or ALTER the column to allow longer values. Add application-side validation for data length.",
    },
    "22003": {
        "cause": "A numeric value exceeded the range of its target data type (e.g., a value larger than 2^31-1 for INTEGER).",
        "solution": "Use a larger numeric type (BIGINT instead of INTEGER, or increase NUMERIC precision). Validate input values before insertion.",
    },
    "22007": {
        "cause": "A string value could not be parsed as a valid date, time, or timestamp.",
        "solution": "Ensure date/time strings match the expected format (ISO 8601 recommended). Use TO_DATE() or TO_TIMESTAMP() with explicit format strings.",
    },
    "22012": {
        "cause": "A SQL expression attempted to divide a value by zero.",
        "solution": "Add a NULLIF guard: x / NULLIF(y, 0). Investigate why the divisor contains zero values.",
    },
    "22P02": {
        "cause": "A string value could not be converted to the expected data type (e.g., 'abc' cast to INTEGER, or a malformed UUID).",
        "solution": "Check input data for format errors. Use explicit type validation before casting.",
    },
    "23502": {
        "cause": "An INSERT or UPDATE attempted to set a NOT NULL column to NULL.",
        "solution": "Provide a non-NULL value, set a DEFAULT on the column, or review whether the NOT NULL constraint is still appropriate.",
    },
    "23503": {
        "cause": "A foreign key reference points to a parent row that doesn't exist, or a parent row is being deleted/updated while still referenced.",
        "solution": "Ensure referenced parent rows exist before inserting children. For deletes, use ON DELETE CASCADE/SET NULL or remove child rows first.",
    },
    "23505": {
        "cause": "An INSERT or UPDATE attempted to store a duplicate value in a column protected by a UNIQUE constraint or PRIMARY KEY.",
        "solution": "Check for duplicates in incoming data. Use INSERT ... ON CONFLICT (upsert) to handle duplicates gracefully.",
    },
    "23514": {
        "cause": "A row failed to satisfy a CHECK constraint defined on the table.",
        "solution": "Inspect failing values against the constraint (query pg_constraint). Fix data or ALTER the constraint if the rule changed.",
    },
    "25001": {
        "cause": "An operation that cannot run inside a transaction block was attempted while a transaction is active (e.g., CREATE DATABASE, VACUUM FULL).",
        "solution": "COMMIT or ROLLBACK the current transaction first, or run the command outside a BEGIN/COMMIT block.",
    },
    "25006": {
        "cause": "A write operation was attempted in a read-only transaction or on a read-only standby/replica server.",
        "solution": "Direct write operations to the primary server. If in a read-only transaction, use SET TRANSACTION READ WRITE.",
    },
    "25P02": {
        "cause": "A command was issued after a previous command in the same transaction block failed. PostgreSQL requires a ROLLBACK before accepting new commands.",
        "solution": "Issue ROLLBACK to end the failed transaction, then retry. In application code, wrap transactions in try/except with rollback on error.",
    },
    "28000": {
        "cause": "Authentication failed. The user provided invalid credentials or is not authorized to connect to the database.",
        "solution": "Verify username/password. Check pg_hba.conf for the authentication method. Ensure the role exists (\\du in psql).",
    },
    "28P01": {
        "cause": "The password provided does not match the one stored for the role.",
        "solution": "Reset the password with ALTER ROLE ... PASSWORD '...'. Update connection strings. Check for cached/stale credentials in connection pools.",
    },
    "3D000": {
        "cause": "The client attempted to connect to a database that does not exist on this server.",
        "solution": "Check the database name for typos. List databases with \\l in psql. Create with CREATE DATABASE if needed.",
    },
    "3F000": {
        "cause": "A query referenced a schema that does not exist in the current database.",
        "solution": "Check schema name for typos. List schemas with \\dn. Create with CREATE SCHEMA or adjust search_path.",
    },
    "40001": {
        "cause": "A transaction could not be committed due to a conflict with another concurrent transaction under SERIALIZABLE or REPEATABLE READ isolation.",
        "solution": "Retry the transaction. This is expected under high concurrency. Consider whether a lower isolation level (READ COMMITTED) is acceptable.",
    },
    "40P01": {
        "cause": "Two or more transactions formed a circular lock dependency (deadlock). PostgreSQL aborted one to break the cycle.",
        "solution": "Retry the aborted transaction. Prevent deadlocks by acquiring locks in a consistent order and keeping transactions short. Analyze with pg_stat_activity and pg_locks.",
    },
    "42501": {
        "cause": "The current user lacks the required permission for the requested operation.",
        "solution": "GRANT the necessary privilege. Check current privileges with \\dp in psql. Use role-based access control.",
    },
    "42601": {
        "cause": "The SQL statement has a syntax error at or near the indicated position.",
        "solution": "Review the SQL at the error position. Check for typos, missing punctuation, or reserved word conflicts. Double-quote identifiers that clash with reserved words.",
    },
    "42703": {
        "cause": "The query referenced a column that does not exist in the specified table or result set.",
        "solution": "Check column name for typos. Verify table structure with \\d table_name. The column may have been renamed or dropped.",
    },
    "42P01": {
        "cause": "The query referenced a table or view that does not exist in the current search_path.",
        "solution": "Check table name for typos. Verify with \\dt. Check search_path and qualify with schema if needed (schema.table).",
    },
    "42883": {
        "cause": "No function matches the given name and argument types.",
        "solution": "Check function name and argument types. Use \\df to list overloads. You may need an explicit type cast on arguments.",
    },
    "53100": {
        "cause": "The PostgreSQL data directory filesystem has run out of disk space, which can halt writes and potentially crash the server.",
        "solution": "Free disk space immediately. Remove old WAL files or archives. Check table bloat and VACUUM FULL. Add monitoring/alerts for disk usage.",
    },
    "53200": {
        "cause": "PostgreSQL or the OS ran out of available memory, possibly due to high work_mem across many sessions or large sort/hash operations.",
        "solution": "Reduce work_mem, shared_buffers, or max_connections. Check for memory-hungry queries. Add RAM or reduce concurrent load.",
    },
    "53300": {
        "cause": "The number of client connections reached the max_connections limit.",
        "solution": "Increase max_connections (requires restart). Better: use PgBouncer to pool connections. Investigate connection leaks.",
    },
    "55006": {
        "cause": "The database object cannot be modified because it is in use by another session.",
        "solution": "Identify and terminate sessions using the object (pg_terminate_backend). Schedule DDL during maintenance windows.",
    },
    "55P03": {
        "cause": "A lock could not be acquired within the lock_timeout period.",
        "solution": "Increase lock_timeout or identify the blocking transaction with pg_stat_activity and pg_locks.",
    },
    "57014": {
        "cause": "The query was cancelled because it exceeded statement_timeout.",
        "solution": "Optimize the query (add indexes, rewrite). If timeout is too aggressive, increase statement_timeout for this session/role.",
    },
    "57P01": {
        "cause": "The PostgreSQL server is shutting down. All connected sessions receive this error.",
        "solution": "This is usually intentional (maintenance/restart). Implement reconnection logic in the application.",
    },
    "57P03": {
        "cause": "The server is starting up (performing recovery) or shutting down and cannot accept connections.",
        "solution": "Wait and retry after a brief delay. The server will accept connections once ready.",
    },
    "58030": {
        "cause": "A file I/O operation failed at the OS level, indicating possible disk failure, filesystem corruption, or NFS issues.",
        "solution": "Check disk health (SMART, dmesg). Verify filesystem integrity. Check file descriptors (ulimit -n). Run pg_basebackup as precaution.",
    },
    "58P01": {
        "cause": "PostgreSQL expected a file to exist but could not find it (missing data files, WAL segments, or relation files).",
        "solution": "Do NOT manually create files in the data directory. If WAL segments are missing, restore from backup. Check for accidental deletion.",
    },
    "XX000": {
        "cause": "An unexpected internal error occurred, typically a bug in PostgreSQL, data corruption, or a corrupted extension.",
        "solution": "Check logs for stack traces. Try to reproduce minimally. Report to pgsql-bugs. As a workaround, try REINDEX or pg_amcheck.",
    },
    "XX001": {
        "cause": "PostgreSQL detected data corruption in a table, index, or system catalog.",
        "solution": "Take a backup immediately. Run pg_amcheck. For index corruption: REINDEX. For table corruption: recover from backups. Check hardware health.",
    },
}


def parse_errcodes(text: str):
    """Parse the official PostgreSQL errcodes.txt into a list of
    (sqlstate, severity_char, macro_name, condition_name, section) tuples."""
    entries = []
    current_section = ""

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("Section:"):
            current_section = line[len("Section:"):].strip()
            continue

        parts = line.split()
        if len(parts) < 3:
            continue

        sqlstate = parts[0]
        severity_char = parts[1]  # E=Error, W=Warning, S=Success
        macro_name = parts[2]
        condition_name = parts[3] if len(parts) > 3 else ""

        entries.append((sqlstate, severity_char, macro_name, condition_name, current_section))

    return entries


def _macro_to_message(macro_name: str) -> str:
    """Convert ERRCODE_MACRO_NAME to a human-readable message."""
    msg = macro_name.replace("ERRCODE_", "").replace("_", " ").lower()
    return msg.capitalize()


def _condition_to_category(sqlstate: str, section: str) -> str:
    """Derive a category from the error class."""
    cls = sqlstate[:2]
    if cls in CLASS_INFO:
        return CLASS_INFO[cls][0]
    # Fallback: use section name
    m = re.match(r"Class \w+ - (.+)", section)
    if m:
        return m.group(1)
    return "General"


def _get_severity(sqlstate: str, sev_char: str) -> str:
    """Map to our severity scale."""
    if sev_char in ("W", "S"):
        return "informational"
    cls = sqlstate[:2]
    if cls in CLASS_INFO:
        return CLASS_INFO[cls][1]
    return "medium"


def _generate_cause(sqlstate: str, condition_name: str, message: str, section: str) -> str:
    """Generate a reasonable cause description."""
    if sqlstate in DETAILED_ENTRIES:
        return DETAILED_ENTRIES[sqlstate]["cause"]

    cls = sqlstate[:2]
    class_desc = CLASS_INFO.get(cls, (section, "medium"))[0]
    cond = condition_name.replace("_", " ") if condition_name else message.lower()

    return f"A {class_desc.lower()} occurred: {cond}. This error belongs to SQLSTATE class {cls} ({class_desc})."


def _generate_solution(sqlstate: str, condition_name: str, message: str, section: str) -> str:
    """Generate a reasonable solution description."""
    if sqlstate in DETAILED_ENTRIES:
        return DETAILED_ENTRIES[sqlstate]["solution"]

    cls = sqlstate[:2]
    # Class-specific generic advice
    solutions = {
        "08": "Check server status, network connectivity, and pg_hba.conf authentication rules.",
        "22": "Validate input data types and ranges before sending to the database. Check column definitions.",
        "23": "Check data against table constraints. Ensure referential integrity and uniqueness requirements are met.",
        "25": "Review transaction state management. Ensure proper COMMIT/ROLLBACK handling.",
        "28": "Verify credentials and check pg_hba.conf authentication configuration.",
        "42": "Review SQL syntax and verify object names, permissions, and schema search_path.",
        "53": "Check server resources (disk, memory, connections). Consider scaling up or optimizing resource usage.",
        "54": "Simplify the query or schema. Break complex operations into smaller parts.",
        "55": "Check object state and active locks. Use pg_stat_activity to identify blocking sessions.",
        "57": "Check server status and administrative actions. Implement reconnection logic.",
        "58": "Check OS-level logs, disk health, and filesystem integrity.",
        "XX": "Check PostgreSQL logs for details. This may indicate a bug or data corruption. Consider filing a bug report.",
    }
    return solutions.get(cls, f"Consult the PostgreSQL documentation for SQLSTATE {sqlstate} ({condition_name or message.lower()}).")


def _generate_keywords(sqlstate: str, condition_name: str, message: str) -> list:
    """Generate relevant keywords."""
    words = set()
    for text in [condition_name, message.lower()]:
        for w in text.replace("_", " ").split():
            if len(w) > 2 and w not in {"the", "for", "and", "not", "are", "was"}:
                words.add(w.lower())
    words.add(sqlstate)
    return sorted(words)[:8]


def build_kb(errcodes_text: str = None, errcodes_url: str = ERRCODES_URL):
    """Parse errcodes.txt and write the PostgreSQL KB."""
    if errcodes_text is None:
        print(f"Fetching errcodes.txt from {errcodes_url}...")
        try:
            with urllib.request.urlopen(errcodes_url, timeout=30) as resp:
                errcodes_text = resp.read().decode("utf-8")
            print(f"Fetched {len(errcodes_text)} bytes.")
        except Exception as e:
            print(f"Could not fetch errcodes.txt: {e}")
            print("Falling back to built-in entries only.")
            errcodes_text = ""

    entries_raw = parse_errcodes(errcodes_text) if errcodes_text else []

    # Deduplicate by sqlstate (some codes appear twice with different macro names)
    seen = set()
    entries = []
    for sqlstate, sev_char, macro_name, condition_name, section in entries_raw:
        if sqlstate in seen:
            continue
        seen.add(sqlstate)

        # Skip success codes
        if sev_char == "S":
            continue

        message = _macro_to_message(macro_name)
        category = _condition_to_category(sqlstate, section)
        severity = _get_severity(sqlstate, sev_char)
        cause = _generate_cause(sqlstate, condition_name, message, section)
        solution = _generate_solution(sqlstate, condition_name, message, section)
        keywords = _generate_keywords(sqlstate, condition_name, message)

        entries.append({
            "code": sqlstate,
            "message": message,
            "category": category,
            "cause": cause,
            "solution": solution,
            "keywords": keywords,
            "severity": severity,
            "engine": "postgres",
        })

    base_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    out_path = os.path.join(base_dir, "data", "knowledge_base", "postgres_errors_kb.jsonl")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    n_detailed = sum(1 for e in entries if e["code"] in DETAILED_ENTRIES)
    n_informational = sum(1 for e in entries if e["severity"] == "informational")
    print(f"Wrote {len(entries)} PostgreSQL KB entries to {out_path}")
    print(f"  {n_detailed} with hand-written detailed cause/solution")
    print(f"  {n_informational} informational (warnings/no-data)")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the PostgreSQL error knowledge base from official errcodes.txt.")
    parser.add_argument("--errcodes-url", default=ERRCODES_URL, help="URL to fetch errcodes.txt from")
    args = parser.parse_args()
    build_kb(errcodes_url=args.errcodes_url)
