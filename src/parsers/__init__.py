"""
parsers package

Per-engine log parsers that all return a common ErrorOccurrence-shaped object.
The engine detection module (src/engine_detection.py) determines which parser
to use; everything downstream (retriever, generator, pipeline) works with the
shared ErrorOccurrence dataclass and doesn't need to know which engine it came from.
"""

from src.log_parser import ErrorOccurrence  # re-export the shared dataclass
from src.parsers.oracle import parse_oracle_log_text, parse_oracle_log_file
from src.parsers.postgres import parse_postgres_log_text, parse_postgres_log_file
from src.parsers.mysql import parse_mysql_log_text, parse_mysql_log_file


def parse_log_text(text: str, engine: str = "oracle", context_window: int = 2):
    """Dispatch to the correct engine-specific parser."""
    if engine == "postgres":
        return parse_postgres_log_text(text, context_window=context_window)
    elif engine == "mysql":
        return parse_mysql_log_text(text, context_window=context_window)
    else:
        return parse_oracle_log_text(text, context_window=context_window)


def parse_log_file(path: str, engine: str = "oracle", context_window: int = 2):
    """Dispatch to the correct engine-specific parser (file variant)."""
    if engine == "postgres":
        return parse_postgres_log_file(path, context_window=context_window)
    elif engine == "mysql":
        return parse_mysql_log_file(path, context_window=context_window)
    else:
        return parse_oracle_log_file(path, context_window=context_window)
