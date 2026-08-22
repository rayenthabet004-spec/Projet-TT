"""
log_parser.py

Extracts Oracle error occurrences from raw log text (alert logs, trace files,
listener logs, application logs that embed Oracle errors, etc.).

Design notes:
- Oracle error codes follow a small number of prefix conventions: ORA-, TNS-,
  RMAN-, PLS-, SP2-, LRM-, KUP-, IMP-, EXP-, UDE-, UDI-, PCC-, LPX-.
  We match the common ones; add more to ERROR_PREFIXES if you hit real logs
  with a prefix not covered here.
- A single physical error "event" in a real alert log is often followed by
  1-3 continuation lines (e.g. object names, extra detail). We capture a
  small context window around each match so the retriever/generator has more
  to work with than just the bare code.
- We keep line numbers and (if present) a timestamp, so a produced report can
  point a human back to the exact spot in the original file.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

ERROR_PREFIXES = [
    # Original hand-picked set
    "ORA", "TNS", "RMAN", "PLS", "SP2", "LRM", "KUP", "IMP", "EXP", "UDE", "UDI", "PCC", "LPX",
    # Added after auditing the full 27,282-entry scraped KB (data/knowledge_base/oracle_errors_kb.jsonl)
    # -- these prefixes are real and were previously silently unmatched by this parser.
    "AUD", "CLSR", "CLSS", "CLST", "CLSU", "CLSW", "CRS", "DBV", "DGM", "DIA", "DRG", "EVM",
    "GIPC", "IMG", "INS", "JMS", "KFED", "KFOD", "LCD", "LFI", "LSX", "NCR", "NDFN", "NID",
    "NMP", "NNC", "NNF", "NNL", "NNO", "NPL", "NZE", "OCI", "PCB", "PGA", "PGU", "PLW",
    "PRCA", "PRCC", "PRCD", "PRCH", "PRCI", "PRCN", "PRCO", "PRCR", "PRCS", "PRCT", "PRCW",
    "PRIF", "PRKA", "PRKC", "PRKE", "PRKH", "PRKN", "PRKO", "PRKP", "PRKR", "PRKU", "PROC",
    "PROT", "PRVF", "PRVP", "QSM", "RDE", "RDJ", "SCLC", "SCLS", "SQL", "VID", "XOQ",
]
# NOTE: if you add more entries to the knowledge base later with new prefixes not seen
# here, re-run: python -c "import json; from collections import Counter; ..." over the
# KB file (see generate_finetune_logs.py's docstring for the one-liner) and update this
# list -- an unmatched prefix means the parser will silently skip those errors entirely.

# Matches things like ORA-01555, TNS-12154, RMAN-03002
ERROR_CODE_RE = re.compile(
    r"\b(?P<prefix>" + "|".join(ERROR_PREFIXES) + r")-(?P<num>\d{3,5})\b"
)

# Oracle network interface connect errors without standard prefix
_NI_CONNECT_RE = re.compile(r"\bFatal NI connect error\s+(?P<num>\d{4,5})\b", re.IGNORECASE)

# A fairly permissive timestamp matcher covering common Oracle alert log
# formats, e.g. "Sun Jul 05 14:23:11 2026" or "2026-07-05T14:23:11.123456+01:00"
TIMESTAMP_PATTERNS = [
    re.compile(r"\b\w{3}\s+\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\d{4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2})?\b"),
]


@dataclass
class ErrorOccurrence:
    code: str  # e.g. "ORA-01555", "23505", "MY-001213"
    line_number: int  # 1-indexed line number in the source file
    raw_line: str
    context: str  # a few lines of surrounding text, joined
    timestamp: Optional[str] = None
    is_pseudo_code: bool = False  # True for synthetic codes like "PG-ERROR" that aren't real DB error codes

    def to_dict(self):
        d = {
            "code": self.code,
            "line_number": self.line_number,
            "raw_line": self.raw_line,
            "context": self.context,
            "timestamp": self.timestamp,
        }
        if self.is_pseudo_code:
            d["is_pseudo_code"] = True
        return d


def _find_nearest_timestamp(lines: List[str], from_index: int) -> Optional[str]:
    """Scan backwards from from_index to find the most recent timestamp line,
    which in real Oracle alert logs often sits on its own line above a block
    of related messages."""
    for i in range(from_index, max(from_index - 25, -1), -1):
        for pat in TIMESTAMP_PATTERNS:
            m = pat.search(lines[i])
            if m:
                return m.group(0)
    return None


def normalize_code(code: str) -> str:
    """Normalize error codes so lookups are consistent regardless of
    zero-padding quirks seen in real Oracle output (e.g. a "signalled
    during:" trailer line sometimes prints "ORA-1652" while the primary
    message line prints "ORA-01652" -- same error, different rendering).
    Pads the numeric part to 5 digits, which matches Oracle's own convention
    for ORA- codes; other prefixes are left at their natural width.
    """
    m = re.match(r"^(?P<prefix>[A-Z]+)-(?P<num>\d+)$", code)
    if not m:
        return code
    prefix, num = m.group("prefix"), m.group("num")
    if prefix == "ORA":
        return f"{prefix}-{int(num):05d}"
    return code


def parse_log_text(text: str, context_window: int = 2) -> List[ErrorOccurrence]:
    """Parse raw log text and return one ErrorOccurrence per matched error code
    occurrence (a code appearing twice yields two occurrences; dedup/counting
    is left to the caller since occurrence frequency is often useful signal).
    """
    lines = text.splitlines()
    raw_matches = []

    for idx, line in enumerate(lines):
        found = False
        for m in ERROR_CODE_RE.finditer(line):
            code = normalize_code(f"{m.group('prefix')}-{m.group('num')}")
            ts = _find_nearest_timestamp(lines, idx)
            raw_matches.append((idx, line, code, ts))
            found = True

        if not found:
            m_ni = _NI_CONNECT_RE.search(line)
            if m_ni:
                code = normalize_code(f"TNS-{m_ni.group('num')}")
                ts = _find_nearest_timestamp(lines, idx)
                raw_matches.append((idx, line, code, ts))

    all_event_indices = [
        idx for idx, line in enumerate(lines)
        if ERROR_CODE_RE.search(line) or _NI_CONNECT_RE.search(line) or any(p.search(line) for p in TIMESTAMP_PATTERNS)
    ]
    occurrences: List[ErrorOccurrence] = []

    for idx, line, code, ts in raw_matches:
        # Context window boundary trimming:
        # Do not include neighboring distinct log events in this occurrence's context window.
        prev_indices = [i for i in all_event_indices if i < idx]
        next_indices = [i for i in all_event_indices if i > idx]
        prev_idx = max(prev_indices) if prev_indices else None
        next_idx = min(next_indices) if next_indices else None

        start = max(0, idx - context_window, (prev_idx + 1) if prev_idx is not None else 0)
        end = min(len(lines), idx + context_window + 1, next_idx if next_idx is not None else len(lines))
        context = "\n".join(lines[start:end])

        occurrences.append(
            ErrorOccurrence(
                code=code,
                line_number=idx + 1,
                raw_line=line.strip(),
                context=context,
                timestamp=ts,
            )
        )

    return occurrences


def parse_log_file(path: str, context_window: int = 2) -> List[ErrorOccurrence]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return parse_log_text(text, context_window=context_window)


def summarize_occurrences(occurrences: List[ErrorOccurrence]):
    """Group occurrences by code and return counts + first/last line numbers.
    Useful for a quick console summary before doing the (more expensive)
    retrieval + generation step per unique code.
    """
    summary = {}
    for occ in occurrences:
        if occ.code not in summary:
            summary[occ.code] = {
                "code": occ.code,
                "count": 0,
                "first_line": occ.line_number,
                "last_line": occ.line_number,
                "example": occ.raw_line,
            }
        summary[occ.code]["count"] += 1
        summary[occ.code]["last_line"] = occ.line_number
    return sorted(summary.values(), key=lambda x: x["count"], reverse=True)


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) != 2:
        print("Usage: python log_parser.py <path_to_log_file>")
        sys.exit(1)

    occs = parse_log_file(sys.argv[1])
    print(f"Found {len(occs)} error occurrences.\n")
    for row in summarize_occurrences(occs):
        print(f"{row['code']:>12}  x{row['count']:<4}  e.g. {row['example'][:80]}")
