"""
mysql.py — MySQL log parser

Extracts error occurrences from MySQL error log files. MySQL has two major
log format generations:

1. MySQL 8.0+ structured format:
   2026-08-20T14:23:11.456789Z 0 [ERROR] [MY-010457] [Server] --initialize specified but the data directory has files in it. Aborting.
   2026-08-20T14:23:11.456789Z 0 [Warning] [MY-013360] [Server] Plugin mysql_native_password reported: ...

2. Classic/legacy format (MySQL 5.x and some 8.x configs):
   2026-08-20 14:23:11 12345 [ERROR] InnoDB: Unable to lock ./ibdata1 error: 11
   ERROR 1045 (28000): Access denied for user 'root'@'localhost'

3. MySQL client error format:
   ERROR 2002 (HY000): Can't connect to local MySQL server through socket ...

Design notes:
- MySQL error codes are numeric (1000-9999 range typically), prefixed with
  MY- in structured logs or just bare numbers in classic format.
- MySQL also has SQLSTATE codes (5-char, shown in parentheses), but we key
  on the MySQL-native numeric code since that's more specific.
- Like Oracle's code normalization, we pad MySQL codes to consistent width.
"""

import re
from typing import List, Optional

from src.log_parser import ErrorOccurrence

# MySQL 8+ structured log format:
# timestamp thread [level] [MY-NNNNNN] [subsystem] message
# Accepts Z, +HH:MM, -HH:MM, or no suffix after fractional seconds
_MYSQL_STRUCTURED_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+(?:Z|[+-]\d{2}:\d{2})?)"
    r"\s+\d+\s+"
    r"\[(?P<level>ERROR|Warning|Note|System)\]\s+"
    r"\[MY-(?P<code>\d{6})\]\s+"
    r"\[(?P<subsystem>\w+)\]\s+"
    r"(?P<message>.+)",
    re.MULTILINE | re.IGNORECASE,
)

# Classic MySQL error log format (various):
# timestamp thread_id [level] message (with optional error code embedded)
_MYSQL_CLASSIC_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2})"
    r".*?"
    r"\[(?P<level>ERROR|Warning|Note)\]\s+"
    r"(?P<message>.+)",
    re.MULTILINE | re.IGNORECASE,
)

# MySQL client/general error: ERROR NNNN (SQLSTATE): message
_MYSQL_CLIENT_RE = re.compile(
    r"^ERROR\s+(?P<code>\d{4,5})\s+\((?P<sqlstate>\w{5})\):\s+(?P<message>.+)",
    re.MULTILINE | re.IGNORECASE,
)

# InnoDB-specific error patterns
_MYSQL_INNODB_RE = re.compile(
    r"InnoDB:\s+(?P<message>.+)",
    re.IGNORECASE,
)

# MySQL timestamp patterns for context scanning
_MYSQL_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b"
)
# Well-known MySQL error numbers for message-based inference
_MYSQL_MSG_TO_CODE = {
    r"Access denied for user": "1045",
    r"Unknown database": "1049",
    r"Table .+ doesn't exist": "1146",
    r"Duplicate entry .+ for key": "1062",
    r"Cannot add or update a child row.*foreign key constraint": "1452",
    r"Cannot delete or update a parent row.*foreign key constraint": "1451",
    r"(?:Transaction )?deadlock (?:found|detected)": "1213",
    r"Lock wait timeout exceeded": "1205",
    r"Too many connections": "1040",
    r"You have an error in your SQL syntax": "1064",
    r"Column .+ cannot be null": "1048",
    r"Data too long for column": "1406",
    r"Incorrect .+ value": "1366",
    r"Out of range value": "1264",
    r"Can't connect to (?:local )?MySQL server": "2002",
    r"Lost connection to MySQL server": "2013",
    r"MySQL server has gone away": "2006",
    r"The table .+ is full": "1114",
    r"Incorrect key file for table": "1034",
    r"Got error \d+ from storage engine": "1030",
    r"Unable to lock": "1015",
    r"Assertion failure": "13183",
    r"Shutdown complete": "0",  # informational
    r"ready for connections": "0",  # informational
}
_MYSQL_MSG_PATTERNS = [(re.compile(pat, re.IGNORECASE), code) for pat, code in _MYSQL_MSG_TO_CODE.items()]

GENERIC_MYSQL_CODES = {"MY-013183", "013183", "13183", "MY-13183"}


def normalize_mysql_code(code: str) -> str:
    """Normalize MySQL error codes to MY-NNNNNN format for consistency."""
    try:
        num = int(code)
        return f"MY-{num:06d}"
    except (ValueError, TypeError):
        return f"MY-{code}"


def _infer_mysql_code(message: str) -> Optional[str]:
    """Try to infer a MySQL error code from the message text."""
    for pat, code in _MYSQL_MSG_PATTERNS:
        if pat.search(message):
            return code
    return None


def _find_nearest_timestamp(lines: List[str], from_index: int) -> Optional[str]:
    """Scan backwards to find the most recent timestamp."""
    for i in range(from_index, max(from_index - 25, -1), -1):
        m = _MYSQL_TIMESTAMP_RE.search(lines[i])
        if m:
            return m.group(0)
    return None


def parse_mysql_log_text(text: str, context_window: int = 2) -> List[ErrorOccurrence]:
    """Parse MySQL log text and return ErrorOccurrence objects.

    Handles MySQL 8+ structured format, classic error log format, and
    MySQL client error format. Only captures ERROR and Warning level lines
    (Note/System are informational and too noisy to capture by default).

    Extraction Hierarchy:
    1. Primary: Message pattern inference (_MYSQL_MSG_TO_CODE) to resolve specific
       errors (reused bracket codes like MY-013183 for FK, deadlock, dup key, missing table).
    2. Secondary: Raw bracket code [MY-NNNNNN] extracted from the log (excluding generic wrapper codes).
    3. Fallback: MY-{level} pseudo-code (marked with is_pseudo_code=True).
    """
    lines = text.splitlines()
    raw_matches = []
    all_structured_indices = []

    for idx, line in enumerate(lines):
        code = None
        level = None
        message = None
        ts_str = None

        # Try MySQL 8+ structured format first (most specific)
        m = _MYSQL_STRUCTURED_RE.match(line)
        if m:
            all_structured_indices.append(idx)
            level = m.group("level").upper()
            code = m.group("code")
            message = m.group("message")
            ts_str = m.group("timestamp")
        else:
            # Try client error format: ERROR NNNN (SQLSTATE): message
            m = _MYSQL_CLIENT_RE.match(line)
            if m:
                all_structured_indices.append(idx)
                level = "ERROR"
                code = m.group("code")
                message = m.group("message")
            else:
                # Try classic format
                m = _MYSQL_CLASSIC_RE.match(line)
                if m:
                    all_structured_indices.append(idx)
                    level = m.group("level").upper()
                    message = m.group("message")
                    ts_str = m.group("timestamp")

        if not m or not message:
            continue

        # Only capture errors and warnings, skip Note/System
        if level not in ("ERROR", "WARNING"):
            continue

        # Extraction hierarchy:
        # 1. Message-pattern inference FIRST (specific error identification)
        inferred = _infer_mysql_code(message)
        if inferred:
            normalized = normalize_mysql_code(inferred)
            pseudo = False
        elif code and normalize_mysql_code(code) not in GENERIC_MYSQL_CODES:
            # 2. Raw bracket code / client code (excluding generic wrapper codes like MY-013183)
            normalized = normalize_mysql_code(code)
            pseudo = False
        else:
            # 3. Fallback pseudo-code
            normalized = f"MY-{level}"
            pseudo = True

        # Skip purely informational messages (shutdown/startup)
        if normalized == "MY-000000":
            continue

        raw_matches.append((idx, line, normalized, pseudo, ts_str))

    occurrences: List[ErrorOccurrence] = []

    for idx, line, normalized, pseudo, ts_str in raw_matches:
        # Context window boundary trimming:
        # Do not include neighboring structured log events in this occurrence's context window.
        prev_indices = [i for i in all_structured_indices if i < idx]
        next_indices = [i for i in all_structured_indices if i > idx]
        prev_idx = max(prev_indices) if prev_indices else None
        next_idx = min(next_indices) if next_indices else None

        start = max(0, idx - context_window, (prev_idx + 1) if prev_idx is not None else 0)
        end = min(len(lines), idx + context_window + 1, next_idx if next_idx is not None else len(lines))
        context = "\n".join(lines[start:end])

        if not ts_str:
            ts_str = _find_nearest_timestamp(lines, idx)

        occurrences.append(
            ErrorOccurrence(
                code=normalized,
                line_number=idx + 1,
                raw_line=line.strip(),
                context=context,
                timestamp=ts_str,
                is_pseudo_code=pseudo,
            )
        )

    return occurrences


def parse_mysql_log_file(path: str, context_window: int = 2) -> List[ErrorOccurrence]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return parse_mysql_log_text(text, context_window=context_window)
