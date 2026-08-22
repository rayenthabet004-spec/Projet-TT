"""
chatbot.py - Interactive DBA AI Assistant for Tunisie Telecom
Provides conversational AI support for database administrators (Oracle, PostgreSQL, MySQL).
Supports Google Gemini API mode and Local FLAN-T5 / KB offline mode.
"""

import os
import re
from typing import Dict, List, Optional
from src.rag.knowledge_base import load_default_kb
from src.rag.retriever import Retriever

DBA_SYSTEM_PROMPT = """Vous êtes "TT-DBA Assistant", l'assistant IA spécialisé de Tunisie Telecom (Direction IT & Exploitation des Systèmes / Subdivision Administration Bases de Données).

VOTRE MISSION EXCLUSIVE :
Vous devez assister les équipes techniques et les administrateurs de bases de données (DBA) de Tunisie Telecom UNIQUEMENT sur les sujets suivants :
1. L'analyse, le diagnostic et l'explication des fichiers de logs de bases de données (Oracle Database, PostgreSQL, MySQL).
2. L'explication des codes d'erreurs (ex: ORA-01555, ORA-00060, erreurs PostgreSQL 42P01, erreurs MySQL 1045/InnoDB, etc.).
3. La fourniture de solutions techniques concrètes, de scripts SQL de remédiation et de bonnes pratiques d'exploitation DBA.
4. L'architecture et le fonctionnement de cette plateforme de triage IA (RAG multi-moteurs, classifieur ML, base de connaissances locale 27 600+ règles, modèles FLAN-T5 et Gemini).

RÈGLES DE GARDE-FOU STRICTES (STRICT GUARDRAILS) :
- DOMAINE STRICT : Vous ne devez JAMAIS répondre à des questions hors sujet (culture générale, météo, actualités, programmation sans rapport avec les bases de données, etc.).
- REFUS POLI DES REQUÊTES HORS DOMAINE : Si l'utilisateur pose une question en dehors des logs de bases de données, du rôle de DBA ou de ce projet, répondez poliment :
  "Je suis l'assistant IA dédié à l'analyse des logs et au support DBA de Tunisie Telecom. Je ne peux répondre qu'aux questions relatives aux erreurs de bases de données (Oracle, PostgreSQL, MySQL) et au diagnostic de vos fichiers logs."
- STYLE & FORMAT :
  * Répondez de manière professionnelle, claire et structurée (en français par défaut).
  * Lorsque vous proposez une commande ou un script de correction (SQL, Bash, RMAN), placez-le toujours dans un bloc de code formaté avec coloration syntaxique (```sql ... ```).
  * Si un rapport d'analyse est fourni dans le contexte de la session, basez prioritairement vos explications sur les erreurs réelles qui y ont été détectées.
"""

_KB = None
_RETRIEVER = None


def _get_retriever() -> Retriever:
    global _KB, _RETRIEVER
    if _RETRIEVER is None:
        _KB = load_default_kb()
        _RETRIEVER = Retriever(_KB)
    return _RETRIEVER


def _load_env_file():
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


def _extract_db_context_summary(report_context: Optional[dict]) -> str:
    """Format the latest analyzed log report as concise context for the LLM."""
    if not report_context or not isinstance(report_context, dict):
        return "(Aucun fichier log n'a encore été analysé dans cette session)."

    engine = report_context.get("engine", "Inconnu")
    findings = report_context.get("findings", [])
    if not findings:
        return f"Dernier log analysé : Moteur {engine}, aucune anomalie détectée."

    lines = [
        f"CONTEXTE DU DERNIER FICHIER LOG ANALYSÉ PAR L'UTILISATEUR :",
        f"- Moteur détecté : {engine.upper()}",
        f"- Nombre total d'erreurs uniques : {len(findings)}",
        "- Liste des anomalies détectées :"
    ]
    for idx, f in enumerate(findings[:8], 1):
        code = f.get("code", "N/A")
        count = f.get("occurrence_count", 1)
        exp = f.get("explanation", {})
        meaning = exp.get("meaning", "")
        lines.append(f"  {idx}. Code [{code}] ({count} occ.) : {meaning}")

    return "\n".join(lines)


def chat_gemini(
    message: str,
    history: List[Dict[str, str]],
    report_context: Optional[dict] = None,
    api_key: Optional[str] = None,
    engine: Optional[str] = None
) -> str:
    """Interactive DBA assistant powered by Google Gemini API."""
    _load_env_file()
    key = api_key or os.environ.get("GEMINI_API_KEY")

    if not key:
        return chat_offline_kb(message, report_context, engine)

    log_ctx = _extract_db_context_summary(report_context)

    # Build conversation payload
    system_instruction = f"{DBA_SYSTEM_PROMPT}\n\n{log_ctx}"

    contents = []
    # Add conversation history
    for item in history[-6:]:  # Keep last 6 turns for concise memory
        role = "user" if item.get("role") == "user" else "model"
        text = item.get("content", "").strip()
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})

    # Add current user message
    contents.append({"role": "user", "parts": [{"text": message}]})

    payload = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 1000
        }
    }
    headers = {"Content-Type": "application/json"}

    models = ["gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-pro-latest", "gemini-3.7-flash"]
    for model_name in models:
        try:
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
            resp = requests.post(url, headers=headers, json=payload, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
            elif resp.status_code in [400, 401, 403]:
                break
        except Exception:
            continue

    return None


def chat_groq(
    message: str,
    history: List[Dict[str, str]],
    report_context: Optional[dict] = None,
    api_key: Optional[str] = None,
    engine: Optional[str] = None
) -> Optional[str]:
    """Interactive DBA assistant powered by Groq API (LLaMA-3.3 / Mixtral)."""
    _load_env_file()
    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        return None

    log_ctx = _extract_db_context_summary(report_context)
    system_msg = f"{DBA_SYSTEM_PROMPT}\n\n{log_ctx}\nTarget Database Engine: {(engine or 'oracle').upper()}."

    messages = [{"role": "system", "content": system_msg}]
    for item in history[-6:]:
        role = "user" if item.get("role") == "user" else "assistant"
        text = item.get("content", "").strip()
        if text:
            messages.append({"role": role, "content": text})

    messages.append({"role": "user", "content": message})

    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]
    for model_name in models:
        try:
            import requests
            url = "https://api.groq.com/openai/v1/chat/completions"
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
                json={"model": model_name, "messages": messages, "temperature": 0.3, "max_tokens": 1000},
                timeout=4
            )
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
            elif resp.status_code in [400, 401, 403]:
                break
        except Exception:
            continue

    return None


def chat_offline_kb(
    message: str,
    report_context: Optional[dict] = None,
    engine: Optional[str] = None
) -> str:
    """100% offline knowledge-base retrieval DBA assistant."""
    # Check for greeting or generic DBA question
    msg_lower = message.lower()

    if any(w in msg_lower for w in ["bonjour", "salut", "hello", "qui es-tu", "qui etes vous"]):
        return (
            "Bonjour ! Je suis **TT-DBA Assistant**, votre assistant d'analyse de logs et de support "
            "bases de données pour **Tunisie Telecom** (Oracle, PostgreSQL, MySQL).\n\n"
            "Vous pouvez me poser une question sur un code d'erreur (ex: `ORA-01555`), me demander un script SQL "
            "de correction, ou des explications sur le dernier log que vous avez analysé."
        )

    # Check for out-of-domain questions
    unrelated_keywords = ["météo", "recette", "film", "football", "musique", "blague", "politique"]
    if any(w in msg_lower for w in unrelated_keywords):
        return (
            "Je suis l'assistant IA dédié à l'analyse des logs et au support DBA de **Tunisie Telecom**.\n\n"
            "Je ne peux répondre qu'aux questions relatives aux erreurs de bases de données "
            "(Oracle, PostgreSQL, MySQL), aux scripts de remédiation et au diagnostic de vos fichiers logs."
        )

    # Search for specific error codes mentioned in the query or report
    error_code_match = re.search(r'\b(ORA-\d+|TNS-\d+|RMAN-\d+|PLS-\d+|MY-\d+|\d{5})\b', message, re.IGNORECASE)
    
    retriever = _get_retriever()
    target_code = None
    if error_code_match:
        target_code = error_code_match.group(1).upper()
    elif report_context and report_context.get("findings"):
        # Use top finding from analyzed log
        target_code = report_context["findings"][0].get("code")

    if target_code:
        engine_target = engine or (report_context.get("engine") if report_context else None)
        retrieved = retriever.retrieve_for_error(target_code, message, k=2, engine=engine_target)
        if retrieved:
            entry, score = retrieved[0]
            return (
                f"### 📋 Diagnostic pour l'erreur **{entry.code}** (Base de connaissances locale TT)\n\n"
                f"**Signification :** {entry.message}\n\n"
                f"**Cause racine probable :** {entry.cause}\n\n"
                f"**Solution & Actions recommandées :**\n"
                f"{entry.solution}\n\n"
                f"*(Mode hors-ligne : réponse certifiée extraite de la base locale de 27 600+ règles)*"
            )

    # General search across KB using user message as query
    top_entries = retriever.retrieve(message, k=2, engine=engine)
    if top_entries:
        entry, score = top_entries[0]
        return (
            f"### 💡 Recommandation DBA pour votre demande :\n\n"
            f"**Élément associé ({entry.code}) :** {entry.message}\n\n"
            f"**Cause possible :** {entry.cause}\n\n"
            f"**Solution recommandée :**\n{entry.solution}\n\n"
            f"*(Réponse générée en mode local hors-ligne)*"
        )

    return (
        "Pourriez-vous préciser le code d'erreur exact (ex: `ORA-01555`, `42P01`) ou le problème rencontré sur votre base ? "
        "Vous pouvez également importer un fichier log dans l'analyseur pour que je puisse examiner directement les incidents."
    )


def handle_chat_request(
    message: str,
    history: List[Dict[str, str]],
    mode: str = "gemini",
    engine: Optional[str] = None,
    report_context: Optional[dict] = None,
    api_key: Optional[str] = None
) -> Dict[str, str]:
    """Entry point for the Chatbot API with cascading fallback (Gemini -> Groq -> Local KB)."""
    mode = (mode or "gemini").lower()
    
    if mode == "t5" or mode == "local" or mode == "mock":
        reply = chat_offline_kb(message, report_context, engine)
        used_mode = "FLAN-T5 / Base Locale"
    elif mode == "groq":
        # 1. Try Groq
        reply = chat_groq(message, history, report_context, api_key, engine)
        used_mode = "Groq (LLaMA-3.3)"
        
        # 2. Fallback to Gemini
        if not reply:
            reply = chat_gemini(message, history, report_context, api_key, engine)
            if reply:
                used_mode = "Google Gemini (Fallback Groq)"

        # 3. Fallback to Local KB
        if not reply:
            reply = chat_offline_kb(message, report_context, engine)
            used_mode = "Base Locale (Fallback)"
    else:  # mode == "gemini"
        # 1. Try Gemini
        reply = chat_gemini(message, history, report_context, api_key, engine)
        used_mode = "Google Gemini"

        # 2. Fallback to Groq
        if not reply:
            reply = chat_groq(message, history, report_context, api_key, engine)
            if reply:
                used_mode = "Groq LLaMA-3.3 (Fallback Gemini)"

        # 3. Fallback to Local KB
        if not reply:
            reply = chat_offline_kb(message, report_context, engine)
            used_mode = "Base Locale (Fallback)"

    return {
        "reply": reply,
        "mode_used": used_mode
    }
