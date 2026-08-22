"""
oracle.py — Oracle log parser

Thin wrapper around the existing src/log_parser.py, which already handles
Oracle logs comprehensively (81 prefixes, code normalization, context window,
timestamp extraction). This module just re-exports those functions under the
consistent per-engine interface expected by src/parsers/__init__.py.
"""

from src.log_parser import (
    parse_log_text as parse_oracle_log_text,
    parse_log_file as parse_oracle_log_file,
    ErrorOccurrence,
    normalize_code,
    ERROR_CODE_RE,
    ERROR_PREFIXES,
)

__all__ = [
    "parse_oracle_log_text",
    "parse_oracle_log_file",
    "ErrorOccurrence",
    "normalize_code",
    "ERROR_CODE_RE",
    "ERROR_PREFIXES",
]
