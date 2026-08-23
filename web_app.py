"""
web_app.py - FastAPI Web Application for Database Log AI Diagnostic Suite
Designed for Tunisie Telecom - IT & Database Administration

Provides REST API endpoints and hosts the modern web dashboard.
"""

import os
import sys
from typing import Optional, List
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Ensure project root is in python path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.rag.pipeline import analyze_log, report_to_markdown
from src.rag.knowledge_base import load_default_kb
from src.rag.retriever import Retriever
from src.engine_detection import detect_engine

# ---------------------------------------------------------------------------
# Module-level singletons -- initialized ONCE at startup, reused on every
# request.  Previously load_default_kb() + Retriever() were called inside
# analyze_log() with no caching, re-parsing 27 622 JSONL entries and
# rebuilding the BM25 inverted index on EVERY HTTP request (~0.78s locally,
# ~2-4s on Railway's slower container FS).  This is now fixed.
# ---------------------------------------------------------------------------
_KB = None
_RETRIEVER = None

app = FastAPI(
    title="Tunisie Telecom - Database Log AI Triage Suite",
    description="Multi-Engine Database Log Incident Analysis powered by AI (Oracle, PostgreSQL, MySQL)",
    version="2.0.0"
)

# CORS middleware for API access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static directory setup
STATIC_DIR = os.path.join(ROOT_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "css"), exist_ok=True)
os.makedirs(os.path.join(STATIC_DIR, "js"), exist_ok=True)


class AnalysisRequest(BaseModel):
    log_text: str
    engine: Optional[str] = "auto"
    mode: Optional[str] = "t5"
    context_window: Optional[int] = 2
    use_classifier: Optional[bool] = True
    filter_informational: Optional[bool] = False
    api_key: Optional[str] = None


@app.on_event("startup")
def startup_warmup():
    """Initialize all heavy resources synchronously at startup.

    Runs BEFORE uvicorn marks the server as ready to accept requests, so the
    first real HTTP request never blocks on a cold KB/BM25 build or T5 load.
    """
    global _KB, _RETRIEVER

    # 1. Load KB + build BM25 index once -- reused on every request
    print("[startup] Loading knowledge base...", flush=True)
    _KB = load_default_kb()
    _RETRIEVER = Retriever(_KB)
    print(f"[startup] KB ready ({len(_KB)} entries, BM25 indexed).", flush=True)

    # 2. Pre-load T5 model into memory synchronously (blocks until done)
    #    This ensures the first request never waits 20+ seconds for a cold load.
    from src.rag.generator import warmup_t5
    warmup_t5()


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Tunisie Telecom Database Log AI Triage Suite",
        "supported_engines": ["Oracle", "PostgreSQL", "MySQL"],
        "default_mode": "t5 (Fine-tuned FLAN-T5 + Knowledge Base)"
    }


@app.get("/api/samples/{engine}")
def get_sample_log(engine: str):
    engine = engine.lower()
    sample_files = {
        "oracle": "oracle_challenging.log",
        "postgres": "postgresql_challenging.log",
        "postgresql": "postgresql_challenging.log",
        "mysql": "mysql_challenging.log",
        "example": "example.log"
    }

    filename = sample_files.get(engine)
    if not filename:
        raise HTTPException(status_code=404, detail=f"No sample available for engine: {engine}")

    file_path = os.path.join(ROOT_DIR, filename)
    if not os.path.isfile(file_path):
        # Fallback to synthetic logs if available
        synth_files = {
            "oracle": "data/synthetic_logs/alert_ttprod1_2026-07-01.log",
            "postgres": "data/synthetic_logs/finetune_corpus_v2/finetune_postgres_000.log",
            "mysql": "data/synthetic_logs/finetune_corpus_v2/finetune_mysql_000.log"
        }
        file_path = os.path.join(ROOT_DIR, synth_files.get(engine, ""))

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Sample log file could not be found.")

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    return {
        "engine": engine,
        "filename": os.path.basename(file_path),
        "content": content
    }


def _run_pipeline(
    log_content: str,
    source_name: str,
    engine: Optional[str] = "auto",
    mode: Optional[str] = "t5",
    context_window: int = 2,
    use_classifier: bool = True,
    filter_informational: bool = False,
    api_key: Optional[str] = None
) -> dict:
    if not log_content.strip():
        raise HTTPException(status_code=400, detail="Provided log content is empty.")

    engine_arg = None if (not engine or engine == "auto") else engine.lower()

    try:
        report_dict = analyze_log(
            log_text=log_content,
            kb=_KB,            # reuse singleton -- avoids 9.78 MB JSONL parse per request
            retriever=_RETRIEVER,  # reuse singleton -- avoids BM25 index rebuild per request
            mode=mode or "t5",
            context_window=context_window or 2,
            use_classifier=use_classifier,
            filter_informational=filter_informational,
            engine=engine_arg,
            api_key=api_key
        )
        
        # Add summary structure for UI compatibility
        report_dict["summary"] = {
            "total_occurrences": report_dict.get("total_error_occurrences", 0),
            "unique_error_codes": report_dict.get("unique_error_codes", len(report_dict.get("findings", []))),
            "total_real_errors": report_dict.get("total_real_errors", 0),
            "total_informational": report_dict.get("total_informational", 0),
            "generation_mode": report_dict.get("generation_mode", mode or "t5")
        }

        # Add metadata & preformatted markdown report
        markdown_text = report_to_markdown(report_dict)
        report_dict["markdown_report"] = markdown_text
        report_dict["source_name"] = source_name

        return report_dict
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Log analysis pipeline failed: {str(e)}")



@app.post("/api/analyze")
def analyze_json_endpoint(req: AnalysisRequest):
    result = _run_pipeline(
        log_content=req.log_text,
        source_name="pasted_text",
        engine=req.engine,
        mode=req.mode or "t5",
        context_window=req.context_window or 2,
        use_classifier=req.use_classifier if req.use_classifier is not None else True,
        filter_informational=req.filter_informational if req.filter_informational is not None else False,
        api_key=req.api_key
    )
    return JSONResponse(content=result)


@app.post("/api/analyze/upload")
async def analyze_file_endpoint(
    file: UploadFile = File(...),
    engine: Optional[str] = Form("auto"),
    mode: Optional[str] = Form("t5"),
    context_window: Optional[int] = Form(2),
    use_classifier: Optional[bool] = Form(True),
    filter_informational: Optional[bool] = Form(False),
    api_key: Optional[str] = Form(None)
):
    raw_bytes = await file.read()
    log_content = raw_bytes.decode("utf-8", errors="replace")
    
    result = _run_pipeline(
        log_content=log_content,
        source_name=file.filename,
        engine=engine,
        mode=mode or "t5",
        context_window=context_window or 2,
        use_classifier=use_classifier if use_classifier is not None else True,
        filter_informational=filter_informational if filter_informational is not None else False,
        api_key=api_key
    )
    return JSONResponse(content=result)


from src.rag.chatbot import handle_chat_request


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []
    mode: Optional[str] = "t5"
    engine: Optional[str] = None
    report_context: Optional[dict] = None
    api_key: Optional[str] = None


@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Le message ne peut pas être vide.")
    
    result = handle_chat_request(
        message=req.message,
        history=req.history or [],
        mode=req.mode or "gemini",
        engine=req.engine,
        report_context=req.report_context,
        api_key=req.api_key
    )
    return JSONResponse(content=result)


# Serve Static Assets
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Tunisie Telecom Log AI Suite</h1><p>Frontend static files loading...</p>")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    is_dev = os.environ.get("ENV", "production") == "development"
    uvicorn.run("web_app:app", host="0.0.0.0", port=port, reload=is_dev)
