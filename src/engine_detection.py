"""
engine_detection.py

Lightweight heuristic-based engine detection: given raw log text, determines
which database engine produced it (Oracle, PostgreSQL, or MySQL) so the
correct per-engine parser can be invoked.

Design notes:
- Regex/heuristic only, NOT a trained classifier (no time budget for that
  within the 2-day scope).
- Works per-file (assume one engine per file/upload), which is the realistic
  case — mixed-engine log files are theoretically possible but vanishingly
  rare in production.
- detect_engine_line() is available if you ever need per-line detection, but
  detect_engine() (per-file) is the primary API used by the pipeline.
"""

import re
from typing import Optional

# --- Oracle patterns ---
# Oracle error prefixes: ORA-, TNS-, RMAN-, PLS-, etc.
_ORACLE_RE = re.compile(
    r"\b(?:ORA|TNS|RMAN|PLS|SP2|LRM|KUP|IMP|EXP|UDE|UDI|PCC|LPX|CRS|DRG"
    r"|PRCA|PRCC|PRCD|PRCH|PRCI|PRCN|PRCO|PRCR|PRCS|PRCT|PRCW"
    r"|PRIF|PRKA|PRKC|PRKE|PRKH|PRKN|PRKO|PRKP|PRKR|PRKU"
    r"|AUD|CLSR|CLSS|CLST|CLSU|CLSW|DBV|DGM|DIA|EVM|GIPC|IMG|INS|JMS"
    r"|KFED|KFOD|LCD|LFI|LSX|NCR|NDFN|NID|NMP|NNC|NNF|NNL|NNO|NPL|NZE"
    r"|OCI|PCB|PGA|PGU|PLW|PROC|PROT|PRVF|PRVP|QSM|RDE|RDJ"
    r"|SCLC|SCLS|SQL|VID|XOQ)-\d{3,5}\b"
)

# --- PostgreSQL patterns ---
# PostgreSQL log lines typically start with a timestamp, then a log level
# like ERROR:, FATAL:, WARNING:, LOG:, followed by the message.
# SQLSTATE codes are 5-character alphanumeric (class 2 chars + subclass 3 chars).
_PG_LOG_LEVEL_RE = re.compile(
    r"(?:ERROR|FATAL|PANIC|WARNING|LOG|DETAIL|HINT|STATEMENT|CONTEXT):\s+",
    re.IGNORECASE,
)
# PostgreSQL often shows SQLSTATE in the log like:  SQLSTATE[42601]  or just mentions it.
# Also, specific PG error formats like "ERROR:  relation ... does not exist"
_PG_SQLSTATE_RE = re.compile(r"\bSQLSTATE\s*\[?\s*(\d{5}|[0-9A-Z]{5})\s*\]?", re.IGNORECASE)
# PostgreSQL-specific keywords that don't appear in Oracle/MySQL logs
_PG_SPECIFIC_RE = re.compile(
    r"\b(?:postgresql|postgres|pg_catalog|pg_stat|pg_class|pg_index|pg_toast"
    r"|shared_buffers|wal_level|max_wal_senders|pg_hba\.conf|pg_ident\.conf"
    r"|pg_ctl|postmaster|bgwriter|autovacuum|pg_dump|pg_restore)\b",
    re.IGNORECASE,
)

# --- MySQL patterns ---
# MySQL 8+ structured log: [ERROR] [MY-NNNNNN] [Server]
_MYSQL_STRUCTURED_RE = re.compile(r"\[(?:ERROR|Warning|Note|System)\]\s*\[MY-(\d{6})\]", re.IGNORECASE)
# Classic MySQL error log: ERROR NNNN (SQLSTATE): message
_MYSQL_CLASSIC_RE = re.compile(r"\bERROR\s+(\d{4})\s*\(\w{5}\)\s*:", re.IGNORECASE)
# MySQL-specific keywords
_MYSQL_SPECIFIC_RE = re.compile(
    r"\b(?:mysqld?|innodb|mariadb|mysql_native_password|caching_sha2_password"
    r"|ibdata1|ib_logfile|binlog|relay[ _]log|gtid_mode|server[_-]id"
    r"|group_replication|galera|MyISAM|InnoDB)\b",
    re.IGNORECASE,
)


def detect_engine_line(line: str) -> Optional[str]:
    """Detect the most likely engine from a single log line.
    Returns 'oracle', 'postgres', 'mysql', or None if ambiguous/unknown."""
    # Oracle — very distinctive prefix-number patterns or NI connect errors
    if _ORACLE_RE.search(line) or re.search(r"\bFatal NI connect error\b", line, re.IGNORECASE):
        return "oracle"

    # MySQL structured format (most distinctive)
    if _MYSQL_STRUCTURED_RE.search(line) or _MYSQL_CLASSIC_RE.search(line):
        return "mysql"

    # PostgreSQL SQLSTATE reference or error level format
    if _PG_SQLSTATE_RE.search(line):
        return "postgres"
    if _PG_LOG_LEVEL_RE.search(line) or re.search(r"\bLINE\s+\d+:", line, re.IGNORECASE):
        return "postgres"

    # Engine-specific keywords as tiebreaker
    if _PG_SPECIFIC_RE.search(line):
        return "postgres"
    if _MYSQL_SPECIFIC_RE.search(line):
        return "mysql"

    return None


def detect_engine(text: str, return_confidence: bool = False):
    """Detect the database engine from a full log file/text block.

    Scans the first ~500 non-empty lines and votes on the most common engine
    signal. Returns 'oracle', 'postgres', or 'mysql'.

    If return_confidence=True, returns (engine, confidence) where confidence
    is a float 0.0-1.0 indicating detection reliability. A confidence of 0.0
    means no engine-specific signal was found and the result is a blind default.
    """
    votes = {"oracle": 0, "postgres": 0, "mysql": 0}
    lines = text.splitlines()[:500]  # scan generously but not the whole file
    non_empty = 0

    for line in lines:
        if not line.strip():
            continue
        non_empty += 1
        engine = detect_engine_line(line)
        if engine:
            votes[engine] += 1

    total_votes = sum(votes.values())

    if total_votes == 0:
        # No engine-specific signal at all — blind default
        result = "oracle"
        confidence = 0.0
    else:
        result = max(votes, key=votes.get)
        # Confidence reflects agreement among votes cast (margin between 1st and 2nd),
        # with total_votes providing a signal sufficiency floor (require >= 3 votes for full 1.0)
        sorted_votes = sorted(votes.values(), reverse=True)
        margin = (sorted_votes[0] - sorted_votes[1]) / total_votes
        sufficiency = min(1.0, total_votes / 3.0)
        confidence = round(margin * sufficiency, 4)

    if return_confidence:
        return result, confidence
    return result


def detect_engine_file(path: str, return_confidence: bool = False):
    """Detect engine from a log file on disk."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return detect_engine(text, return_confidence=return_confidence)

