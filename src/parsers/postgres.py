"""
postgres.py — PostgreSQL log parser

Extracts error occurrences from PostgreSQL log files. PostgreSQL's error code
system is fundamentally different from Oracle's:
- Codes are 5-character alphanumeric SQLSTATE values (e.g. 23505, 42601, 08006)
  with NO letter prefix (unlike Oracle's ORA-NNNNN).
- The first 2 characters are the error class, the last 3 are the subclass.
- Log lines typically follow the format:
    2026-08-20 14:23:11.456 UTC [12345] ERROR:  duplicate key value violates unique constraint "pk_users"
    2026-08-20 14:23:11.456 UTC [12345] DETAIL:  Key (id)=(42) already exists.
    2026-08-20 14:23:11.456 UTC [12345] STATEMENT:  INSERT INTO users ...

  Sometimes the SQLSTATE code appears inline:
    ERROR:  relation "foo" does not exist (SQLSTATE 42P01)

Design notes (lesson #2 from BUILD_PLAN):
- The regex pattern is designed for what SQLSTATE actually looks like, NOT a
  reuse of Oracle's PREFIX-NNNNN pattern shape.
- PostgreSQL log format is highly configurable (log_line_prefix), so we match
  multiple common formats rather than requiring one exact shape.
"""

import re
from typing import List, Optional

from src.log_parser import ErrorOccurrence

# PostgreSQL log levels that indicate an error/warning/notice worth capturing
_PG_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\s*\w+)?)"
    r".*?"
    r"(?P<level>FATAL|PANIC|ERROR|WARNING):\s+(?P<message>.+)",
    re.MULTILINE,
)

# SQLSTATE code appearing in the log line, e.g. "(SQLSTATE 42P01)" or "SQLSTATE[23505]"
_PG_SQLSTATE_INLINE_RE = re.compile(
    r"\(?\bSQLSTATE\s*\[?\s*(?P<code>[0-9A-Z]{5})\s*\]?\)?",
    re.IGNORECASE,
)

# Simpler format: just "ERROR: message" without a timestamp prefix
_PG_SIMPLE_RE = re.compile(
    r"^(?P<level>FATAL|PANIC|ERROR|WARNING):\s+(?P<message>.+)",
    re.MULTILINE,
)

# PostgreSQL timestamp patterns for context scanning
_PG_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\s*[A-Z]{2,5})?\b"
)

# Well-known error message patterns mapped to their SQLSTATE codes,
# for cases where the SQLSTATE isn't printed inline in the log.
# This is a curated subset — the full mapping lives in the KB.
_PG_MSG_TO_SQLSTATE = {
    r"duplicate key value violates unique constraint": "23505",
    r"null value in column .+ violates not-null constraint": "23502",
    r"violates foreign key constraint": "23503",
    r"violates check constraint": "23514",
    r"column .+ does not exist": "42703",
    r"relation .+ does not exist": "42P01",
    r"function .+ does not exist": "42883",
    r"syntax error at or near": "42601",
    r"permission denied for": "42501",
    r"password authentication failed": "28P01",
    r"role .+ does not exist": "42704",
    r"database .+ does not exist": "3D000",
    r"could not connect to server": "08001",
    r"connection refused": "08001",
    r"the database system is shutting down": "57P03",
    r"the database system is starting up": "57P03",
    r"too many connections": "53300",
    r"out of memory": "53200",
    r"disk full": "53100",
    r"deadlock detected": "40P01",
    r"could not serialize access": "40001",
    r"statement timeout": "57014",
    r"lock timeout": "55P03",
    r"division by zero": "22012",
    r"invalid input syntax": "22P02",
    r"value too long for type": "22001",
    r"canceling statement due to": "57014",
    r"could not open file": "58P01",
    r"data directory .+ has wrong ownership": "58P01",
    r"requested WAL segment .+ has already been removed": "58P01",
    r"numeric field overflow": "22003",
    r"could not obtain lock on row": "55P03",
    r"current transaction is aborted.*commands ignored": "25P02",
    r"raise_exception": "P0001",
    r"remaining connection slots are reserved": "53300",
    r"sorry,\s*too many clients already": "53300",
    r"too many clients already": "53300",
}
_PG_MSG_PATTERNS = [(re.compile(pat, re.IGNORECASE), code) for pat, code in _PG_MSG_TO_SQLSTATE.items()]


def _infer_sqlstate(message: str) -> Optional[str]:
    """Try to extract or infer a SQLSTATE code from a PostgreSQL error message."""
    # First: explicit SQLSTATE in the message
    m = _PG_SQLSTATE_INLINE_RE.search(message)
    if m:
        return m.group(1).upper()

    # Second: pattern matching on well-known message phrases
    for pat, code in _PG_MSG_PATTERNS:
        if pat.search(message):
            return code

    return None


def _find_nearest_timestamp(lines: List[str], from_index: int) -> Optional[str]:
    """Scan backwards to find the most recent timestamp."""
    for i in range(from_index, max(from_index - 20, -1), -1):
        m = _PG_TIMESTAMP_RE.search(lines[i])
        if m:
            return m.group(0)
    return None


def parse_postgres_log_text(text: str, context_window: int = 2) -> List[ErrorOccurrence]:
    """Parse PostgreSQL log text and return ErrorOccurrence objects."""
    lines = text.splitlines()
    raw_matches = []
    all_event_indices = []

    for idx, line in enumerate(lines):
        m = _PG_LOG_LINE_RE.match(line)
        if not m:
            m = _PG_SIMPLE_RE.match(line)

        if not m:
            continue

        level = m.group("level").upper()
        message = m.group("message")

        # Track any distinct event start line as a context boundary
        all_event_indices.append(idx)

        # Skip DETAIL/HINT/STATEMENT continuation lines — they're context,
        # not separate errors
        if level in ("DETAIL", "HINT", "STATEMENT", "CONTEXT"):
            continue

        sqlstate = _infer_sqlstate(message)
        if sqlstate:
            code = sqlstate
            pseudo = False
        else:
            # Use level as fallback pseudo-code so we don't silently drop errors
            code = f"PG-{level}"
            pseudo = True

        ts_str = None
        try:
            ts_str = m.group("timestamp").strip()
        except (IndexError, AttributeError):
            pass

        raw_matches.append((idx, line, code, pseudo, ts_str))

    occurrences: List[ErrorOccurrence] = []

    for idx, line, code, pseudo, ts_str in raw_matches:
        # Context window boundary trimming:
        # Do not include neighboring distinct log events in this occurrence's context window.
        prev_indices = [i for i in all_event_indices if i < idx]
        next_indices = [i for i in all_event_indices if i > idx]
        prev_idx = max(prev_indices) if prev_indices else None
        next_idx = min(next_indices) if next_indices else None

        start = max(0, idx - context_window, (prev_idx + 1) if prev_idx is not None else 0)
        end = min(len(lines), idx + context_window + 1, next_idx if next_idx is not None else len(lines))
        context = "\n".join(lines[start:end])

        if not ts_str:
            ts_str = _find_nearest_timestamp(lines, idx)

        occurrences.append(
            ErrorOccurrence(
                code=code,
                line_number=idx + 1,
                raw_line=line.strip(),
                context=context,
                timestamp=ts_str,
                is_pseudo_code=pseudo,
            )
        )

    return occurrences


def parse_postgres_log_file(path: str, context_window: int = 2) -> List[ErrorOccurrence]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return parse_postgres_log_text(text, context_window=context_window)
