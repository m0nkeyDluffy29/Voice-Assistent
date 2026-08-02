"""
server.py — FastAPI backend server
Phase 5: Desktop UI Layer

Exposes all agent capabilities as a REST API so the React frontend
can communicate with the Python backend.

All endpoints talk to the same backend modules built in Phases 1-4.
The server runs locally on 127.0.0.1:8000 — never exposed to the internet.

Endpoints:
    POST /feed/text          — save a typed message
    POST /feed/voice         — save a voice recording (audio file upload)
    POST /ask/text           — ask a question, get answer + context
    GET  /memories/recent    — get recent messages
    GET  /memories/search    — semantic search
    GET  /beliefs            — get belief index
    GET  /stats              — get all stats
    POST /summarise          — run weekly summariser
    POST /beliefs/rebuild    — rebuild belief index
    GET  /health             — health check
    GET  /ws/ask             — WebSocket for streaming answers (Phase 5+)

Start with:
    python main.py --serve
    # or directly:
    uvicorn backend.api.server:app --host 127.0.0.1 --port 8000 --reload
"""

import os
import sys
import json
import tempfile
import asyncio
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title       = "Personal AI Agent API",
    description = "Your digital self — powered by your own memories",
    version     = "1.0.0",
)

# Allow the React dev server (port 5173 for Vite) and Tauri (any origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["http://localhost:5173", "http://localhost:3000", "tauri://localhost"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class FeedTextRequest(BaseModel):
    text: str
    source: str = "text"    # 'text' | 'voice'

class AskRequest(BaseModel):
    query:        str
    language:     Optional[str] = None    # Auto-detect if None
    speak_answer: bool = False            # True = also speak via TTS

class SearchRequest(BaseModel):
    query:   str
    top_k:   int = 5
    language: Optional[str] = None

class SummariseRequest(BaseModel):
    days:  int  = 7
    force: bool = False

# ---------------------------------------------------------------------------
# Startup: initialise database
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    from backend.ingest.storage import init_db
    init_db()
    print("[API] Server ready.")

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Quick check that the server and all modules are reachable."""
    status = {
        "status":   "ok",
        "phase1":   True,
        "phase2":   False,
        "phase3":   False,
        "phase4":   False,
    }
    try:
        from backend.memory.store import get_store_stats
        status["phase2"] = True
    except ImportError:
        pass
    try:
        from backend.reasoning.llm_core import ask
        status["phase3"] = True
    except ImportError:
        pass
    try:
        from backend.output.tts_engine import get_tts
        status["phase4"] = True
    except ImportError:
        pass
    return status

# ---------------------------------------------------------------------------
# FEED endpoints — save memories
# ---------------------------------------------------------------------------

@app.post("/feed/text")
async def feed_text(req: FeedTextRequest):
    """
    Save a typed or dictated message to memory.

    Body: { "text": "...", "source": "text" }
    Returns: { "saved": bool, "language": str, "is_opinion": bool, "id": str }
    """
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    from backend.ingest.preprocessor import preprocess
    from backend.ingest.storage import save_message

    try:
        msg   = preprocess(req.text.strip(), source=req.source)
        saved = save_message(msg)
        return {
            "saved":      saved,
            "id":         msg["id"],
            "language":   msg["language"],
            "is_opinion": msg["entities"].get("is_opinion", False),
            "word_count": msg["word_count"],
            "duplicate":  not saved,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/feed/voice")
async def feed_voice(audio: UploadFile = File(...)):
    """
    Transcribe an audio file and save it as a memory.

    Multipart upload: audio file (.wav / .mp3 / .webm)
    Returns: { "transcribed": str, "saved": bool, "language": str, ... }
    """
    from backend.ingest.listener import transcribe_file
    from backend.ingest.preprocessor import preprocess
    from backend.ingest.storage import save_message

    # Save upload to temp file
    suffix = os.path.splitext(audio.filename or "audio.wav")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content  = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        transcribed = transcribe_file(tmp_path)
        text        = transcribed["text"].strip()

        if not text:
            return {"saved": False, "transcribed": "", "error": "No speech detected"}

        msg   = preprocess(text, source="voice", force_language=transcribed.get("language"))
        saved = save_message(msg)

        return {
            "saved":      saved,
            "transcribed": text,
            "id":          msg["id"],
            "language":    msg["language"],
            "is_opinion":  msg["entities"].get("is_opinion", False),
            "duplicate":   not saved,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

# ---------------------------------------------------------------------------
# ASK endpoints — generate answers from memory
# ---------------------------------------------------------------------------

@app.post("/ask/text")
async def ask_text(req: AskRequest):
    """
    Ask a question and get an answer drawn from your memories.

    Body: { "query": "...", "language": "english", "speak_answer": false }
    Returns: {
        "answer": str,
        "language": str,
        "context_count": int,
        "had_context": bool,
        "sources": [ { "text", "source", "score", "timestamp" } ]
    }
    """
    from backend.reasoning.llm_core import ask
    from backend.ingest.language_utils import detect_language

    language = req.language or detect_language(req.query)

    try:
        result = ask(
            query        = req.query,
            language     = language,
            speak_answer = req.speak_answer,
        )

        # Serialize context items (not JSON-serializable natively)
        sources = []
        for item in result.get("context_items", []):
            sources.append({
                "text":      item.text,
                "source":    item.source,
                "score":     round(getattr(item, "final_score", item.relevance_score), 3),
                "timestamp": item.timestamp,
                "language":  item.language,
            })

        return {
            "answer":        result["answer"],
            "language":      language,
            "context_count": result["context_count"],
            "had_context":   result["had_context"],
            "sources":       sources,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {str(e)}")


@app.post("/ask/voice")
async def ask_voice(audio: UploadFile = File(...), speak_answer: bool = True):
    """
    Voice question → transcribe → ask → speak answer.
    Returns same shape as /ask/text plus transcription.
    """
    from backend.ingest.listener import transcribe_file
    from backend.ingest.language_utils import detect_language
    from backend.reasoning.llm_core import ask

    suffix = os.path.splitext(audio.filename or "q.wav")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await audio.read())
        tmp_path = tmp.name

    try:
        transcribed = transcribe_file(tmp_path)
        query       = transcribed["text"].strip()
        if not query:
            return {"error": "No speech detected", "answer": ""}

        language = transcribed.get("language", "en")
        # Map Whisper lang codes to our format
        lang_map = {"en": "english", "hi": "hindi"}
        language = lang_map.get(language, "english")

        result   = ask(query=query, language=language, speak_answer=speak_answer)
        sources  = [
            {
                "text":      item.text,
                "source":    item.source,
                "score":     round(getattr(item, "final_score", item.relevance_score), 3),
                "timestamp": item.timestamp,
            }
            for item in result.get("context_items", [])
        ]
        return {
            "transcribed":   query,
            "answer":        result["answer"],
            "language":      language,
            "context_count": result["context_count"],
            "had_context":   result["had_context"],
            "sources":       sources,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

# ---------------------------------------------------------------------------
# Memory endpoints
# ---------------------------------------------------------------------------

@app.get("/memories/recent")
async def get_recent(limit: int = 20, language: str = None):
    """
    Get the most recent saved memories.
    Query params: ?limit=20&language=english
    """
    from backend.ingest.storage import get_recent_messages
    messages = get_recent_messages(limit=limit, language=language)
    # Sanitise for JSON — parse entities_json back to dict
    clean = []
    for m in messages:
        m_copy = dict(m)
        if "entities_json" in m_copy:
            try:
                m_copy["entities"] = json.loads(m_copy.pop("entities_json"))
            except Exception:
                m_copy.pop("entities_json", None)
        clean.append(m_copy)
    return {"messages": clean, "count": len(clean)}


@app.get("/memories/search")
async def search_memories(q: str, top_k: int = 5, language: str = None):
    """
    Semantic search over memories.
    Query params: ?q=your+question&top_k=5
    """
    from backend.memory.store import search_memories as _search
    try:
        results = _search(q, top_k=top_k, language=language)
        return {"results": results, "query": q, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/memories/{message_id}")
async def delete_memory(message_id: str):
    """Delete a specific memory by ID."""
    from backend.ingest.storage import get_connection
    with get_connection() as conn:
        conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    return {"deleted": message_id}

# ---------------------------------------------------------------------------
# Beliefs endpoints
# ---------------------------------------------------------------------------

@app.get("/beliefs")
async def get_beliefs(limit: int = 20):
    """Get the top beliefs from the belief index."""
    try:
        from backend.memory.belief_index import get_top_beliefs, get_all_topics, get_belief_count
        beliefs = get_top_beliefs(limit=limit)
        topics  = get_all_topics()
        count   = get_belief_count()
        return {"beliefs": beliefs, "topics": topics, "total": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/beliefs/rebuild")
async def rebuild_beliefs():
    """Rebuild the belief index from all opinion messages."""
    try:
        from backend.memory.belief_index import build_belief_index
        result = build_belief_index()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Summaries endpoints
# ---------------------------------------------------------------------------

@app.post("/summarise")
async def summarise(req: SummariseRequest):
    """Generate a weekly memory summary."""
    try:
        from backend.memory.summariser import run_weekly_summary
        result = run_weekly_summary(days=req.days, force=req.force)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/summaries")
async def get_summaries():
    """Get all stored summaries."""
    try:
        from backend.memory.summariser import get_all_summaries
        summaries = get_all_summaries()
        return {"summaries": summaries, "count": len(summaries)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Stats endpoint
# ---------------------------------------------------------------------------

@app.get("/stats")
async def get_stats():
    """Return all memory stats — SQLite + ChromaDB."""
    from backend.ingest.storage import get_stats as _sqlite_stats
    stats = {"sqlite": _sqlite_stats()}
    try:
        from backend.memory.store import get_store_stats
        stats["chroma"] = get_store_stats()
    except ImportError:
        stats["chroma"] = None
    try:
        from backend.memory.belief_index import get_belief_count
        stats["beliefs"] = get_belief_count()
    except ImportError:
        stats["beliefs"] = None
    return stats

# ---------------------------------------------------------------------------
# WebSocket — streaming ask (for real-time UI updates)
# ---------------------------------------------------------------------------

@app.websocket("/ws/ask")
async def websocket_ask(websocket: WebSocket):
    """
    WebSocket endpoint for streaming answers token by token.

    Client sends:  { "query": "...", "language": "english" }
    Server sends:  { "type": "token", "content": "..." }   (streaming)
                   { "type": "done",  "context_count": N } (finished)
                   { "type": "error", "message": "..." }   (on error)
    """
    await websocket.accept()
    try:
        while True:
            data    = await websocket.receive_json()
            query   = data.get("query", "").strip()
            language = data.get("language", "english")

            if not query:
                await websocket.send_json({"type": "error", "message": "Empty query"})
                continue

            # Run the blocking LLM call in a thread pool
            from backend.reasoning.llm_core import ask
            loop   = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: ask(query=query, language=language, speak_answer=False)
            )

            # Stream the answer word by word for a typing effect
            words = result["answer"].split()
            for i, word in enumerate(words):
                await websocket.send_json({
                    "type":    "token",
                    "content": word + (" " if i < len(words) - 1 else ""),
                })
                await asyncio.sleep(0.03)   # ~33 words/sec typing effect

            await websocket.send_json({
                "type":          "done",
                "context_count": result["context_count"],
                "had_context":   result["had_context"],
            })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass