"""
summariser.py — Weekly digest generator
Phase 2: Memory Layer

Every week (or on demand) this reads all messages from the past 7 days,
sends them to the local Ollama LLM, and generates a compact summary of:
- Key topics you talked about
- Decisions you made
- Recurring patterns or themes
- Your emotional tone

The summary is stored in both SQLite (for records) and ChromaDB (for
semantic search), so Phase 3 can retrieve it alongside raw memories.

This runs locally — no internet, no API key.
"""

import os
import uuid
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager

import ollama

from backend.memory.store import add_summary

# ---------------------------------------------------------------------------
# SQLite table for summaries (separate from messages table)
# ---------------------------------------------------------------------------

DB_DIR  = os.path.join(os.path.dirname(__file__), "../../data/raw_logs")
DB_PATH = os.path.join(DB_DIR, "conversations.db")

SUM_DIR  = os.path.join(os.path.dirname(__file__), "../../data/summaries")


@contextmanager
def get_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_summaries_table():
    """Create the summaries table if it doesn't exist."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS summaries (
                id              TEXT PRIMARY KEY,
                period_start    TEXT NOT NULL,
                period_end      TEXT NOT NULL,
                summary_text    TEXT NOT NULL,
                message_count   INTEGER NOT NULL DEFAULT 0,
                dominant_lang   TEXT NOT NULL DEFAULT 'english',
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)


# ---------------------------------------------------------------------------
# Prompts for the local LLM
# ---------------------------------------------------------------------------

SUMMARY_PROMPT = """You are helping someone build a personal memory system.
Below are messages a person recorded about their own life, thoughts, and opinions
over the past week. Your job is to write a compact summary of this week.

Rules:
- Write in third person ("The person believes...", "This week they...")
- Focus on: key opinions, decisions made, recurring themes, emotional patterns
- Keep it under 200 words
- Do NOT add any information that isn't in the messages
- Do NOT give advice or judge anything
- If messages are in Hindi or Hinglish, summarise in English

Messages from this week:
{messages}

Write the weekly summary now:"""


TOPIC_EXTRACT_PROMPT = """From the messages below, extract the main topics discussed.
Return ONLY a JSON array of short topic strings (2-4 words each), no explanation.
Example: ["morning routines", "work stress", "family values"]

Messages:
{messages}

JSON array:"""


# ---------------------------------------------------------------------------
# Core summariser
# ---------------------------------------------------------------------------

def _call_llm(prompt: str, model: str = "mistral") -> str:
    """Call the local Ollama LLM and return the response text."""
    try:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3}   # Low temp = more factual, less creative
        )
        return response["message"]["content"].strip()
    except Exception as e:
        print(f"[Summariser] LLM error: {e}")
        print("[Summariser] Make sure Ollama is running: ollama serve")
        raise


def summarise_messages(messages: list[dict], model: str = "mistral") -> str:
    """
    Generate a weekly summary from a list of message dicts.

    Args:
        messages: list of message dicts (from storage.get_messages_since)
        model:    Ollama model name (default: mistral)

    Returns:
        Summary text string
    """
    if not messages:
        return "No messages found for this period."

    # Join all message texts with separators
    joined = "\n---\n".join(
        f"[{m['language']}] {m['text']}" for m in messages
    )

    prompt = SUMMARY_PROMPT.format(messages=joined)
    summary = _call_llm(prompt, model)
    return summary


def extract_topics(messages: list[dict], model: str = "mistral") -> list[str]:
    """
    Extract the main topics from a set of messages.

    Returns:
        List of topic strings e.g. ["morning habits", "work decisions"]
    """
    if not messages:
        return []

    joined = "\n".join(m["text"] for m in messages[:30])  # Cap at 30 to keep prompt short
    prompt = TOPIC_EXTRACT_PROMPT.format(messages=joined)

    try:
        raw = _call_llm(prompt, model)
        # Strip markdown fences if LLM added them
        raw = raw.replace("```json", "").replace("```", "").strip()
        topics = json.loads(raw)
        return [t for t in topics if isinstance(t, str)][:10]
    except (json.JSONDecodeError, Exception) as e:
        print(f"[Summariser] Topic extraction failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Weekly summary workflow
# ---------------------------------------------------------------------------

def run_weekly_summary(
    days: int = 7,
    model: str = "mistral",
    force: bool = False,
) -> dict:
    """
    Generate and store the weekly summary.

    Args:
        days:   How many days to look back (default 7)
        model:  Ollama model to use
        force:  If True, generate even if one already exists for this period

    Returns:
        {
            "summary_id":   str,
            "summary_text": str,
            "period_start": str,
            "period_end":   str,
            "message_count": int,
            "topics":       list,
            "skipped":      bool
        }
    """
    init_summaries_table()

    now   = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    start_iso = start.isoformat()
    end_iso   = now.isoformat()

    # Check if summary for this period already exists
    if not force:
        with get_connection() as conn:
            existing = conn.execute("""
                SELECT id FROM summaries
                WHERE period_start >= ?
                LIMIT 1
            """, (start_iso,)).fetchone()
            if existing:
                print(f"[Summariser] Summary already exists for this period. Use force=True to regenerate.")
                return {"skipped": True, "reason": "already_exists"}

    # Pull messages from SQLite
    from backend.ingest.storage import get_messages_since
    messages = get_messages_since(start_iso)

    if not messages:
        print("[Summariser] No messages in this period — nothing to summarise.")
        return {"skipped": True, "reason": "no_messages"}

    print(f"[Summariser] Summarising {len(messages)} messages from the past {days} days...")

    # Generate summary + topics
    summary_text = summarise_messages(messages, model)
    topics       = extract_topics(messages, model)

    # Dominant language
    lang_counts = {}
    for m in messages:
        lang_counts[m["language"]] = lang_counts.get(m["language"], 0) + 1
    dominant_lang = max(lang_counts, key=lang_counts.get)

    summary_id = str(uuid.uuid4())

    # Save to SQLite
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO summaries
                (id, period_start, period_end, summary_text, message_count, dominant_lang)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (summary_id, start_iso, end_iso, summary_text, len(messages), dominant_lang))

    # Save to text file (human-readable backup)
    os.makedirs(SUM_DIR, exist_ok=True)
    filename = f"summary_{now.strftime('%Y-%m-%d')}.txt"
    filepath = os.path.join(SUM_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"Period: {start_iso[:10]} → {end_iso[:10]}\n")
        f.write(f"Messages: {len(messages)}\n")
        f.write(f"Topics: {', '.join(topics)}\n")
        f.write(f"\n{summary_text}\n")

    # Embed into ChromaDB for semantic search
    add_summary(
        summary_id = summary_id,
        text       = summary_text,
        metadata   = {
            "period_start":  start_iso,
            "period_end":    end_iso,
            "message_count": len(messages),
            "dominant_lang": dominant_lang,
            "topics":        json.dumps(topics),
        }
    )

    print(f"[Summariser] Summary saved: {filepath}")
    print(f"[Summariser] Topics: {topics}")

    return {
        "summary_id":    summary_id,
        "summary_text":  summary_text,
        "period_start":  start_iso,
        "period_end":    end_iso,
        "message_count": len(messages),
        "topics":        topics,
        "skipped":       False,
    }


def get_all_summaries() -> list[dict]:
    """Retrieve all stored summaries from SQLite."""
    init_summaries_table()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM summaries ORDER BY period_start DESC
        """).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Weekly Summariser Test ===\n")
    result = run_weekly_summary(days=7)
    if not result.get("skipped"):
        print(f"\nSummary:\n{result['summary_text']}")
        print(f"\nTopics: {result['topics']}")
    else:
        print(f"Skipped: {result.get('reason')}")