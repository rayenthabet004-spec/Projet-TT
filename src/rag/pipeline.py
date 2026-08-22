"""
pipeline.py

End-to-end orchestration: log file -> parsed errors -> retrieval -> generation
-> report (JSON + human-readable markdown).

Supports Oracle, PostgreSQL, and MySQL logs via automatic engine detection.
Design choice: we analyze each *unique* error code once (not once per raw
occurrence) to avoid redundant/expensive LLM calls when the same error
repeats hundreds of times in a log, which is the realistic case. Occurrence
count and line numbers for every instance are still preserved in the report.
"""

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, List

from src.engine_detection import detect_engine
from src.parsers import parse_log_text as multi_parse
from src.log_parser import ErrorOccurrence
from src.rag.generator import Explanation, generate
from src.rag.knowledge_base import KnowledgeBase, load_default_kb
from src.rag.retriever import Retriever


_CLASSIFIER = None
_CLASSIFIER_LOADED = False


def _get_classifier():
    global _CLASSIFIER, _CLASSIFIER_LOADED
    if not _CLASSIFIER_LOADED:
        try:
            from src.classifier.classify import ErrorClassifier
            _CLASSIFIER = ErrorClassifier.load()
        except Exception:
            _CLASSIFIER = None
        _CLASSIFIER_LOADED = True
    return _CLASSIFIER


def _group_by_code(occurrences: List[ErrorOccurrence]) -> Dict[str, List[ErrorOccurrence]]:
    grouped: Dict[str, List[ErrorOccurrence]] = {}
    for occ in occurrences:
        if getattr(occ, "is_pseudo_code", False):
            # Do not merge distinct pseudo-codes together; group by code + normalized raw message
            key = f"{occ.code}::{occ.raw_line.strip()}"
        else:
            key = occ.code
        grouped.setdefault(key, []).append(occ)
    return grouped


def analyze_log(
    log_text: str,
    kb: KnowledgeBase = None,
    retriever: Retriever = None,
    mode: str = "t5",
    context_window: int = 2,
    top_k: int = 3,
    use_classifier: bool = True,
    filter_informational: bool = False,
    engine: str = None,
) -> dict:
    """Analyze raw log text end-to-end and return a report dict.

    Args:
        engine: 'oracle', 'postgres', 'mysql', or None for auto-detection.
    """
    if kb is None:
        kb = load_default_kb()
    if retriever is None:
        retriever = Retriever(kb)

    # Auto-detect engine if not specified
    detection_confidence = None
    if engine is None:
        engine, detection_confidence = detect_engine(log_text, return_confidence=True)

    clf = _get_classifier() if use_classifier else None

    occurrences = multi_parse(log_text, engine=engine, context_window=context_window)
    grouped = _group_by_code(occurrences)

    findings = []
    total_real_errors = 0
    total_informational = 0

    for group_key, occs in grouped.items():
        representative = occs[0]  # use the first occurrence's context for retrieval/generation
        code = representative.code

        classification_dict = None
        if clf is not None:
            try:
                res = clf.predict(representative.raw_line, representative.context)
                classification_dict = res.to_dict()
                classification_dict["label"] = "REAL ERROR" if res.is_real_error else "INFORMATIONAL"
                if res.is_real_error:
                    total_real_errors += 1
                else:
                    total_informational += 1
            except Exception:
                classification_dict = None

        if filter_informational and classification_dict and not classification_dict.get("is_real_error", True):
            continue

        is_pseudo = getattr(representative, "is_pseudo_code", False)
        retrieved = retriever.retrieve_for_error(
            code, representative.context, k=top_k, is_pseudo_code=is_pseudo, engine=engine
        )
        explanation = generate(
            code=code,
            raw_line=representative.raw_line,
            context=representative.context,
            retrieved=retrieved,
            mode=mode,
            engine=engine,
        )
        finding = {
            "code": code,
            "occurrence_count": len(occs),
            "line_numbers": [o.line_number for o in occs],
            "first_seen_timestamp": occs[0].timestamp,
            "example_raw_line": representative.raw_line,
            "retrieved_kb_codes": [e.code for e, _ in retrieved],
            "explanation": explanation.to_dict(),
        }
        if classification_dict:
            finding["classification"] = classification_dict

        findings.append(finding)

    # sort: most frequent errors first (usually the most actionable signal)
    findings.sort(key=lambda f: f["occurrence_count"], reverse=True)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": engine,
        "engine_detection_confidence": detection_confidence,
        "total_error_occurrences": len(occurrences),
        "unique_error_codes": len(grouped),
        "total_real_errors": total_real_errors if clf is not None else None,
        "total_informational": total_informational if clf is not None else None,
        "generation_mode": mode,
        "findings": findings,
    }
    if detection_confidence is not None and detection_confidence < 0.1:
        report["engine_detection_warning"] = (
            f"Database engine could not be reliably identified (confidence={detection_confidence:.2f}). "
            f"Defaulted to '{engine}'. Results may be inaccurate. "
            f"Use --engine to specify the engine explicitly."
        )
    return report


def analyze_log_file(
    path: str,
    kb: KnowledgeBase = None,
    retriever: Retriever = None,
    mode: str = "t5",
    context_window: int = 2,
    top_k: int = 3,
    use_classifier: bool = True,
    filter_informational: bool = False,
    engine: str = None,
) -> dict:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    report = analyze_log(
        text,
        kb=kb,
        retriever=retriever,
        mode=mode,
        context_window=context_window,
        top_k=top_k,
        use_classifier=use_classifier,
        filter_informational=filter_informational,
        engine=engine,
    )
    report["source_file"] = os.path.abspath(path)
    return report


def report_to_markdown(report: dict) -> str:
    lines = []
    lines.append(f"# Database Log Analysis Report")
    lines.append("")
    engine_label = report.get('engine', 'Unknown').title()
    lines.append(f"**Engine detected:** {engine_label}  ")
    if "source_file" in report:
        lines.append(f"**Source file:** `{report['source_file']}`  ")
    lines.append(f"**Generated at:** {report['generated_at']}  ")
    lines.append(f"**Total error occurrences:** {report['total_error_occurrences']}  ")
    lines.append(f"**Unique error codes:** {report['unique_error_codes']}  ")
    if report.get("total_real_errors") is not None:
        lines.append(f"**Real errors / Informational:** {report['total_real_errors']} real / {report['total_informational']} info  ")
    lines.append(f"**Generation mode:** {report['generation_mode']}  ")
    lines.append("")
    lines.append("---")
    lines.append("")

    for f in report["findings"]:
        exp = f["explanation"]
        clf_info = ""
        if "classification" in f and f["classification"]:
            label = f["classification"].get("label", "REAL ERROR" if f["classification"].get("is_real_error") else "INFORMATIONAL")
            conf = f["classification"].get("confidence", 0.0)
            clf_info = f"Classification: {label} ({conf:.1%} confidence) | "

        lines.append(f"## {f['code']}  (seen {f['occurrence_count']}x, lines: {f['line_numbers'][:10]}{'...' if len(f['line_numbers']) > 10 else ''})")
        lines.append("")
        lines.append(f"**Example log line:** `{f['example_raw_line']}`")
        lines.append("")
        lines.append(f"**Meaning:** {exp['meaning']}")
        lines.append("")
        lines.append(f"**Likely cause:** {exp['likely_cause']}")
        lines.append("")
        lines.append(f"**Suggested solution:** {exp['suggested_solution']}")
        lines.append("")
        lines.append(f"*{clf_info}Confidence: {exp['confidence']} | Source: {exp['source']} | KB refs: {', '.join(f['retrieved_kb_codes']) or 'none'}*")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def save_report(report: dict, out_dir: str, basename: str = None) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    if basename is None:
        basename = f"report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    json_path = os.path.join(out_dir, f"{basename}.json")
    md_path = os.path.join(out_dir, f"{basename}.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report_to_markdown(report))

    return {"json": json_path, "markdown": md_path}
