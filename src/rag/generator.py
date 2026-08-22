"""
generator.py

Generation layer: takes an error occurrence + retrieved knowledge base
context, and produces a final structured explanation (meaning / likely
cause / suggested solution) grounded in that context.

Modes:
  - "t5"    : deterministic KB lookup on confident exact matches (score >= 999),
              falling back to the locally fine-tuned FLAN-T5 model for non-exact
              or uncertain errors.
  - "mock"  : internal deterministic output built directly from retrieved KB
              entries (used as exact-match short-circuit and offline test fallback).
"""

import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.rag.knowledge_base import KBEntry

SYSTEM_PROMPT = """You are an assistant helping a database operations team quickly \
triage Oracle Database error messages found in log files. You will be given:
1. The error code and the raw log line(s) where it appeared (with a few lines \
of surrounding context).
2. A small set of retrieved knowledge-base entries that are likely relevant \
(these may or may not be an exact match for the error).

Your job:
- Explain, in plain language, what the error means.
- State the most likely cause given the log context (be specific to the \
context when possible, not just generic).
- Suggest a concrete, actionable solution or next diagnostic step.
- If the retrieved knowledge base entries don't seem to actually match the \
error code, say so plainly rather than forcing a fit.
- Keep the answer concise: a short paragraph per section, not an essay.
- Base your answer on the provided context; do not invent Oracle behavior \
you're not confident about.

Respond in this exact structure:
MEANING: <1-2 sentences>
LIKELY_CAUSE: <1-3 sentences>
SUGGESTED_SOLUTION: <1-3 sentences, concrete and actionable>
CONFIDENCE: <high|medium|low>
"""


@dataclass
class Explanation:
    code: str
    meaning: str
    likely_cause: str
    suggested_solution: str
    confidence: str
    source: str  # "kb_exact_match" | "llm" | "llm_no_kb_match"

    def to_dict(self):
        return {
            "code": self.code,
            "meaning": self.meaning,
            "likely_cause": self.likely_cause,
            "suggested_solution": self.suggested_solution,
            "confidence": self.confidence,
            "source": self.source,
        }


def _build_user_prompt(code: str, raw_line: str, context: str, retrieved: List[Tuple[KBEntry, float]]) -> str:
    kb_block_lines = []
    for entry, score in retrieved:
        kb_block_lines.append(
            f"- [{entry.code}] {entry.message}\n"
            f"  category: {entry.category}\n"
            f"  cause: {entry.cause}\n"
            f"  solution: {entry.solution}\n"
            f"  (retrieval score: {score:.2f})"
        )
    kb_block = "\n".join(kb_block_lines) if kb_block_lines else "(no relevant knowledge base entries found)"

    return f"""ERROR CODE: {code}

RAW LOG LINE:
{raw_line}

SURROUNDING CONTEXT:
{context}

RETRIEVED KNOWLEDGE BASE ENTRIES:
{kb_block}

Now produce the structured explanation described in your instructions."""


def _map_label_to_field(label: str) -> Optional[str]:
    """Map canonical and near-miss model label variants to the 4 canonical fields."""
    lbl = label.upper().strip()
    if lbl in ("MEANING", "SUMMARY", "DESCRIPTION", "EXPLANATION", "ERROR_MEANING", "ERROR_SUMMARY"):
        return "meaning"
    if lbl in ("SUGGESTED_CAUSE", "POSSIBLE_CAUSE", "ROOT_CAUSE", "CAUSE") or lbl.startswith("LIKELY_"):
        return "likely_cause"
    if lbl.startswith("SUGGESTED_") or lbl.startswith("REPORTED_") or lbl in ("SOLUTION", "ACTION", "RECOMMENDED_ACTION", "RECOMMENDATION", "FIX", "NEXT_STEPS"):
        return "suggested_solution"
    if lbl.startswith("CONFIDENCE") or lbl in ("CERTAINTY",):
        return "confidence"
    return None


def _parse_structured_response(text: str) -> dict:
    """Parse the MEANING / LIKELY_CAUSE / SUGGESTED_SOLUTION / CONFIDENCE
    structure (and recognized near-miss label variants) back out of the
    model's plain-text response.

    Uses regex lookahead instead of splitting on newlines to support T5's
    continuous one-line outputs, and recognizes label variants (e.g.
    LIKELY_DETAIL, SUGGESTED_INVALUE, REPORTED_SOLUTION).
    """
    fields = {"meaning": "", "likely_cause": "", "suggested_solution": "", "confidence": "medium"}
    label_pattern = re.compile(
        r"\b([A-Za-z]+(?:_[A-Za-z0-9]+)*)\s*:\s*(.*?)(?=\b[A-Za-z]+(?:_[A-Za-z0-9]+)*\s*:|$)",
        re.DOTALL,
    )
    for m in label_pattern.finditer(text):
        raw_label = m.group(1)
        target_field = _map_label_to_field(raw_label)
        if target_field:
            val = m.group(2).strip()
            if fields[target_field] and target_field != "confidence":
                fields[target_field] = f"{fields[target_field]} {val}".strip()
            elif val:
                fields[target_field] = val

    if not fields["confidence"]:
        fields["confidence"] = "medium"
    return fields


def _extract_message_from_raw_line(raw_line: str, code: str) -> Optional[str]:
    """Extract the specific error message text from a raw log line."""
    if not raw_line:
        return None
    line = raw_line.strip()

    # 1. Oracle style: "RMAN-03009: failure of backup command..." or "ORA-00060: deadlock..."
    m = re.search(r'\b' + re.escape(code) + r'[:\s]+(?P<msg>[^\n\r]+)', line, re.IGNORECASE)
    if m:
        msg = m.group("msg").strip()
        if msg:
            return msg

    # 2. MySQL structured: "... [ERROR] [MY-001264] [Server] Out of range value..."
    m = re.search(r'\[MY-\d+\]\s*\[[^\]]+\]\s*(?P<msg>[^\n\r]+)', line)
    if m:
        msg = m.group("msg").strip()
        if msg:
            return msg

    # 3. PostgreSQL: "... ERROR: duplicate key value..."
    m = re.search(r'\b(?:ERROR|FATAL|PANIC|WARNING):\s*(?P<msg>[^\n\r]+)', line)
    if m:
        msg = m.group("msg").strip()
        if msg:
            return msg

    return None


def _derive_exact_match_meaning(entry_message: str, raw_line: str, code: str) -> str:
    """Derive human-facing meaning text for an exact match.
    If the KB entry contains raw template placeholders like 'string' or '%s',
    or if raw_line provides the instantiated text, use the actual rendered message."""
    if not entry_message:
        extracted = _extract_message_from_raw_line(raw_line, code)
        return extracted or ""

    has_placeholder = bool(re.search(r'\bstring\b|%[sd]', entry_message, re.IGNORECASE))
    if has_placeholder:
        extracted = _extract_message_from_raw_line(raw_line, code)
        if extracted:
            return extracted
        return re.sub(r'\bstring\b', '<value>', entry_message, flags=re.IGNORECASE)

    return entry_message


def generate_mock(
    code: str,
    raw_line: str,
    context: str,
    retrieved: List[Tuple[KBEntry, float]],
) -> Explanation:
    """Offline/test fallback that constructs a structured explanation directly from the
    retrieved KB entry. Used when there's a confident exact match, or when
    running the pipeline without an API key configured."""
    if retrieved:
        top_entry, top_score = retrieved[0]
        is_exact = top_score >= 999.0
        if is_exact:
            meaning = _derive_exact_match_meaning(top_entry.message, raw_line, code)
            return Explanation(
                code=code,
                meaning=meaning,
                likely_cause=top_entry.cause,
                suggested_solution=top_entry.solution,
                confidence="high",
                source="kb_exact_match",
            )
        # No exact code match: the KB entry below is only a *lexically similar*
        # neighbor, not a confirmed explanation of this specific code. Be
        # explicit about that rather than presenting borrowed content as if
        # it directly explains an unrelated code (a real failure mode hit in
        # testing: an unrelated code got matched to "archiver error" just
        # because both mentioned "archiv-"/"log"). This is exactly the kind
        # of case the "llama"/"auto" LLM mode is meant to catch and reason
        # about properly -- mock mode can only flag it, not resolve it.
        return Explanation(
            code=code,
            meaning=f"No exact knowledge base entry for {code}. Closest related entry found: '{top_entry.message}' ({top_entry.code}) -- treat this as a possibly-unrelated suggestion, not a confirmed match.",
            likely_cause="Not confirmed -- this code is not yet in the knowledge base, so the cause below is only a guess based on keyword overlap, not a verified explanation.",
            suggested_solution=f"Verify manually (Oracle docs / My Oracle Support) before acting. If it turns out relevant: {top_entry.solution}",
            confidence="low",
            source="kb_lexical_match_unconfirmed",
        )
    return Explanation(
        code=code,
        meaning="No matching knowledge base entry found for this code.",
        likely_cause="Unknown -- this error code is not yet in the knowledge base.",
        suggested_solution="Add this code to the knowledge base, or consult Oracle's official error documentation / My Oracle Support directly.",
        confidence="low",
        source="no_match",
    )


# NOTE: Ollama/Llama generation modes have been removed. The project exclusively
# uses the fine-tuned T5 model (with deterministic exact-match KB short-circuit).


_T5_MODEL_CACHE = {}  # model_dir -> (tokenizer, model) -- avoid reloading from disk on every call

_models_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "models"))
_multi_engine_path = os.path.join(_models_dir, "multi_engine_t5_model")
DEFAULT_T5_MODEL_DIR = _multi_engine_path if os.path.isdir(_multi_engine_path) else os.path.join(_models_dir, "oracle_log_t5_model")


def _load_t5(model_dir: str):
    if model_dir in _T5_MODEL_CACHE:
        return _T5_MODEL_CACHE[model_dir]

    try:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    except ImportError as e:
        raise RuntimeError(
            "The 'torch' and 'transformers' packages are required for generate_t5(). "
            "Install them with: pip install torch transformers sentencepiece"
        ) from e

    if not os.path.isdir(model_dir):
        raise FileNotFoundError(
            f"No T5 model found at {model_dir}. Train it with "
            f"notebook/oracle_log_t5_finetune_kaggle.ipynb, download the resulting "
            f"oracle_log_t5_model.zip, and extract it to this path."
        )

    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_dir)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    model.eval()

    _T5_MODEL_CACHE[model_dir] = (tokenizer, model)
    return tokenizer, model


from src.log_parser import normalize_code


def _sanitize_hallucinated_codes(text: str, valid_codes: set) -> str:
    """Sanitize fabricated code citations from model output that do not match
    either the target code or any retrieved candidate."""
    if not text:
        return text

    # Matches prefixes like ORA-12345, MY-123456, TNS-12345, or other engine codes
    code_pattern = re.compile(r"\b([A-Z]{2,6}-\d{3,6})\b", re.IGNORECASE)

    def replace_if_hallucinated(match):
        token = match.group(1)
        norm_token = normalize_code(token).upper()
        if norm_token in valid_codes or token.upper() in valid_codes:
            return token
        return "an unconfirmed related issue"

    cleaned = code_pattern.sub(replace_if_hallucinated, text)

    # Clean up formatting artifacts like "to the MY.", "toMY-", "to BY-..."
    cleaned = re.sub(r"\bto\s+the\s+MY\b(?:\.\d+)?", "to an unconfirmed issue", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bto([A-Z]{2,6}-\d+)", r"to \1", cleaned)
    cleaned = re.sub(r"\bto\s+BY-\d+\b", "to an unconfirmed issue", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def generate_t5(
    code: str,
    raw_line: str,
    context: str,
    retrieved: List[Tuple[KBEntry, float]],
    model_dir: str = DEFAULT_T5_MODEL_DIR,
    max_source_length: int = 512,
    max_new_tokens: int = 200,
    engine: str = "oracle",
) -> Explanation:
    """Calls the locally fine-tuned FLAN-T5/BART model directly via the
    `transformers` library (NOT through Ollama -- encoder-decoder models like
    T5 aren't well supported by Ollama/llama.cpp's GGUF format, unlike the
    decoder-only model generate_local() talks to).

    CRITICAL: this must use the exact same source-text format the model was
    TRAINED on (see build_finetune_dataset_v2.py): per-engine instruction +
    "\\n\\n" + context. The instruction must name the correct engine so
    the model uses the right vocabulary/domain (Oracle vs PostgreSQL vs MySQL).
    """
    from src.data_generation.build_finetune_dataset_v2 import INSTRUCTIONS

    instruction = INSTRUCTIONS.get(engine, INSTRUCTIONS["oracle"])

    tokenizer, model = _load_t5(model_dir)

    # Build retrieved knowledge block (same format as training data)
    kb_lines = []
    for entry, score in (retrieved or []):
        kb_lines.append(
            f"- [{entry.code}] {entry.message}\n"
            f"  cause: {entry.cause}\n"
            f"  solution: {entry.solution}\n"
            f"  (score: {score:.1f})"
        )
    kb_block = "\n".join(kb_lines) if kb_lines else "(no relevant knowledge base entries found)"

    # Match training format: instruction + "\n\n" + context + "\n\nRETRIEVED KNOWLEDGE:\n" + kb_block
    source_text = (
        instruction + "\n\n"
        + context + "\n\n"
        + "RETRIEVED KNOWLEDGE:\n"
        + kb_block
    )
    # Left-truncation preserves the crucial RETRIEVED KNOWLEDGE block at the end
    # while staying strictly within the 512-token budget the model was trained on.
    tokenizer.truncation_side = "left"
    inputs = tokenizer(
        source_text,
        return_tensors="pt",
        truncation=True,
        max_length=max_source_length,
    ).to(model.device)

    import torch
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            repetition_penalty=1.3,
            no_repeat_ngram_size=3,
        )

    text = tokenizer.decode(output_ids[0], skip_special_tokens=True)
    parsed = _parse_structured_response(text)

    # FIX 7: Backfill empty fields from top retrieved KB entry instead of shipping blanks
    if retrieved:
        top_entry = retrieved[0][0]
        if not parsed["meaning"] and top_entry.message:
            parsed["meaning"] = top_entry.message
        if not parsed["likely_cause"] and top_entry.cause:
            parsed["likely_cause"] = top_entry.cause
        if not parsed["suggested_solution"] and top_entry.solution:
            parsed["suggested_solution"] = top_entry.solution

    # FIX 2: Guardrail against digit-level code hallucinations
    valid_codes = {normalize_code(code).upper(), code.upper()}
    if retrieved:
        for entry, _ in retrieved:
            valid_codes.add(normalize_code(entry.code).upper())
            valid_codes.add(entry.code.upper())

    for field in ("meaning", "likely_cause", "suggested_solution"):
        if parsed.get(field):
            parsed[field] = _sanitize_hallucinated_codes(parsed[field], valid_codes)

    source = "t5_local" if retrieved else "t5_local_no_kb_match"
    return Explanation(
        code=code,
        meaning=parsed["meaning"],
        likely_cause=parsed["likely_cause"],
        suggested_solution=parsed["suggested_solution"],
        confidence=parsed["confidence"],
        source=source,
    )


def _load_env_file():
    """Automatically load .env into os.environ if present."""
    candidates = [
        os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
        os.path.abspath(".env")
    ]
    for env_path in candidates:
        if os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip('"').strip("'")
                            if k and not os.environ.get(k):
                                os.environ[k] = v
            except Exception:
                pass


_load_env_file()


def generate_gemini(
    code: str,
    raw_line: str,
    context: str,
    retrieved: List[Tuple[KBEntry, float]],
    api_key: Optional[str] = None,
    engine: str = "oracle",
) -> Explanation:
    """Hybrid LLM generation via Google Gemini API."""
    _load_env_file()
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        exp = generate_mock(code, raw_line, context, retrieved)
        exp.source = "mock_fallback (no API key)"
        return exp

    user_prompt = _build_user_prompt(code, raw_line, context, retrieved)
    full_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Target Database Engine: {engine.upper()}.\n\n"
        f"{user_prompt}"
    )

    payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 800}
    }
    headers = {"Content-Type": "application/json"}

    # Supported and active Gemini models
    models = ["gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-pro-latest", "gemini-3.7-flash"]
    for model_name in models:
        try:
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text = parts[0].get("text", "")
                        parsed = _parse_structured_response(text)
                        
                        # Backfill if any field missing
                        if retrieved:
                            top_entry = retrieved[0][0]
                            if not parsed["meaning"] and top_entry.message:
                                parsed["meaning"] = top_entry.message
                            if not parsed["likely_cause"] and top_entry.cause:
                                parsed["likely_cause"] = top_entry.cause
                            if not parsed["suggested_solution"] and top_entry.solution:
                                parsed["suggested_solution"] = top_entry.solution

                        return Explanation(
                            code=code,
                            meaning=parsed["meaning"] or "Explication générée par le modèle Gemini.",
                            likely_cause=parsed["likely_cause"] or "Anomalie identifiée dans le contexte du log.",
                            suggested_solution=parsed["suggested_solution"] or "Vérifier la configuration du serveur.",
                            confidence=parsed["confidence"] or "high",
                            source=f"gemini_llm ({model_name})"
                        )
        except Exception:
            continue

    # Fallback to deterministic mock if API call fails
    fallback_exp = generate_mock(code, raw_line, context, retrieved)
    fallback_exp.source = "gemini_api_error_fallback_to_kb"
    return fallback_exp


def generate(
    code: str,
    raw_line: str,
    context: str,
    retrieved: List[Tuple[KBEntry, float]],
    mode: str = "t5",
    t5_model_dir: str = DEFAULT_T5_MODEL_DIR,
    engine: str = "oracle",
    api_key: Optional[str] = None,
) -> Explanation:
    """Main entry point used by the pipeline.

    mode:
      "mock"    - deterministic KB-only path (no model inference).
      "gemini"  - Google Gemini cloud LLM reasoning with KB context.
      "t5"      - deterministic KB lookup on confident exact matches (score >= 999),
                  falling back to the locally fine-tuned FLAN-T5 model for non-exact
                  or uncertain errors.
    """
    if mode == "mock":
        return generate_mock(code, raw_line, context, retrieved)

    if mode == "gemini":
        return generate_gemini(
            code=code,
            raw_line=raw_line,
            context=context,
            retrieved=retrieved,
            api_key=api_key,
            engine=engine,
        )

    # FIX 1: Exact-match short-circuit MUST always apply before calling generate_t5()
    if retrieved and retrieved[0][1] >= 999.0:
        return generate_mock(code, raw_line, context, retrieved)

    # Call T5 generation for non-exact or uncertain cases
    return generate_t5(
        code=code,
        raw_line=raw_line,
        context=context,
        retrieved=retrieved,
        model_dir=t5_model_dir,
        engine=engine,
    )
