"""
knowledge_base.py

Loads the error knowledge base (JSONL) into memory and exposes it both as
a code -> entry lookup (for exact matches) and as a flat list (for the
BM25 retriever to index). Supports multi-engine KBs (Oracle, PostgreSQL,
MySQL) via the optional 'engine' field on each entry.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class KBEntry:
    code: str
    message: str
    category: str
    cause: str
    solution: str
    keywords: List[str] = field(default_factory=list)
    severity: str = "unknown"
    engine: str = "oracle"

    def searchable_text(self) -> str:
        """Text blob used for BM25 indexing -- combine everything that might
        help match a noisy log line to this entry."""
        return " ".join([
            self.code,
            self.message,
            self.category,
            self.cause,
            self.solution,
            " ".join(self.keywords),
        ])

    def to_dict(self):
        return {
            "code": self.code,
            "message": self.message,
            "category": self.category,
            "cause": self.cause,
            "solution": self.solution,
            "keywords": self.keywords,
            "severity": self.severity,
            "engine": self.engine,
        }


class KnowledgeBase:
    def __init__(self, entries: List[KBEntry]):
        self.entries = entries
        self.by_code: Dict[str, KBEntry] = {e.code: e for e in entries}

    @classmethod
    def load(cls, path: str) -> "KnowledgeBase":
        entries = []
        # KBEntry field names for filtering unknown keys (forward compat)
        _fields = {f.name for f in KBEntry.__dataclass_fields__.values()}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                # Filter to known fields so extra keys in JSONL don't blow up
                filtered = {k: v for k, v in d.items() if k in _fields}
                entries.append(KBEntry(**filtered))
        return cls(entries)

    def get_exact(self, code: str) -> Optional[KBEntry]:
        return self.by_code.get(code)

    def __len__(self):
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)


_KB_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "knowledge_base")
)

# Prefer combined KB if it exists, fall back to Oracle-only
_COMBINED_KB_PATH = os.path.join(_KB_DIR, "combined_errors_kb.jsonl")
_ORACLE_KB_PATH = os.path.join(_KB_DIR, "oracle_errors_kb.jsonl")
DEFAULT_KB_PATH = _COMBINED_KB_PATH if os.path.isfile(_COMBINED_KB_PATH) else _ORACLE_KB_PATH


def load_default_kb() -> KnowledgeBase:
    return KnowledgeBase.load(DEFAULT_KB_PATH)
