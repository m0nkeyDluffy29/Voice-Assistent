"""
storage.py — Local SQLite database for raw conversation logs
Phase 1 + Phase 2 update

All data stays on-device. No cloud. No network.

Tables:
    messages    — every conversation message (timestamped)
    sessions    — session metadata (when you last talked to the agent)

Phase 2 change:
    save_message() now auto-embeds into ChromaDB after every SQLite write.
    If Phase 2 packages aren't installed yet, this silently skips — fully
    backward compatible with Phase 1.
"""

import os
import json
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Optional

# ---------------------------------------------------------------------------
# Database path — stored in data/raw_logs/
# ---------------------------------------------------------------------------

DB_DIR = os.path.join(os.path.dirname(__file__), "../../data/raw_logs")
DB_PATH = os.path.join(DB_DIR, "conversations.db")


# ---------------------------------------------------------------------------
# Connection manager
# ---------------------------------------------------------------------------

@contextmanager
def get_connection():
    """Context manager for SQLite connections."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row      # Rows behave like dicts
    conn.execute("PRAGMA journal_mode=WAL")    # Better concurrent access
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema setup
# ---------------------------------------------------------------------------

def init_db():
    """
    Create all tables if they don't exist.
    Safe to call on every startup.
    """
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id              TEXT PRIMARY KEY,
                text            TEXT NOT NULL,
                raw_text        TEXT NOT NULL,
                language        TEXT NOT NULL DEFAULT 'english',
                source          TEXT NOT NULL DEFAULT 'text',
                is_opinion      INTEGER NOT NULL DEFAULT 0,
                entities_json   TEXT NOT NULL DEFAULT '{}',
                session_id      TEXT NOT NULL,
                word_count      INTEGER NOT NULL DEFAULT 0,
                is_duplicate    INTEGER NOT NULL DEFAULT 0,
                fingerprint     TEXT NOT NULL,
                timestamp       TEXT NOT NULL,
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id);

            CREATE INDEX IF NOT EXISTS idx_messages_timestamp
                ON messages(timestamp);

            CREATE INDEX IF NOT EXISTS idx_messages_language
                ON messages(language);

            CREATE INDEX IF NOT EXISTS idx_messages_fingerprint
                ON messages(fingerprint);

            CREATE TABLE IF NOT EXISTS sessions (
                session_id      TEXT PRIMARY KEY,
                started_at      TEXT NOT NULL,
                ended_at        TEXT,
                message_count   INTEGER NOT NULL DEFAULT 0,
                languages_used  TEXT NOT NULL DEFAULT '[]'
            );
        """)
    print(f"[Storage] Database ready at: {DB_PATH}")


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def save_message(message: dict) -> bool:
    """
    Save a preprocessed message to the database.

    Skips duplicates (checked via fingerprint).

    Args:
        message: dict from preprocessor.preprocess()

    Returns:
        True if saved, False if skipped (duplicate)
    """
    # Skip if already marked as duplicate by preprocessor
    if message.get("is_duplicate"):
        print(f"[Storage] Skipping duplicate: {message['text'][:50]}...")
        return False

    # Double-check against DB fingerprints
    if fingerprint_exists(message["fingerprint"]):
        print(f"[Storage] Already in DB (fingerprint match): {message['text'][:50]}...")
        return False

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO messages
                (id, text, raw_text, language, source, is_opinion,
                 entities_json, session_id, word_count, is_duplicate,
                 fingerprint, timestamp)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message["id"],
            message["text"],
            message["raw_text"],
            message["language"],
            message["source"],
            int(message["entities"].get("is_opinion", False)),
            json.dumps(message["entities"]),
            message["session_id"],
            message["word_count"],
            int(message["is_duplicate"]),
            message["fingerprint"],
            message["timestamp"],
        ))

        # Upsert session record
        conn.execute("""
            INSERT INTO sessions (session_id, started_at, message_count, languages_used)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                message_count   = message_count + 1,
                ended_at        = excluded.started_at
        """, (
            message["session_id"],
            message["timestamp"],
            json.dumps([message["language"]]),
        ))

    print(f"[Storage] Saved message {message['id'][:8]}... ({message['language']}, {message['word_count']} words)")

    # ── Phase 2 hook: auto-embed into ChromaDB ──────────────────────────────
    # Tries to embed immediately. Silently skips if Phase 2 isn't installed yet.
    try:
        from backend.memory.store import add_memory
        add_memory(message)
    except ImportError:
        pass    # Phase 2 not installed yet — that's fine
    except Exception as e:
        print(f"[Storage] Warning: embedding failed (non-fatal): {e}")
    # ────────────────────────────────────────────────────────────────────────

    return True


def save_messages_batch(messages: list[dict]) -> dict:
    """
    Save multiple messages. Returns stats.
    """
    saved = skipped = 0
    for msg in messages:
        if save_message(msg):
            saved += 1
        else:
            skipped += 1
    return {"saved": saved, "skipped": skipped}


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def fingerprint_exists(fingerprint: str) -> bool:
    """Check if a message with this fingerprint already exists."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM messages WHERE fingerprint = ? LIMIT 1",
            (fingerprint,)
        ).fetchone()
    return row is not None


def get_message(message_id: str) -> Optional[dict]:
    """Fetch a single message by ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
    return dict(row) if row else None


def get_recent_messages(limit: int = 50, language: str = None) -> list[dict]:
    """
    Fetch the most recent messages.

    Args:
        limit:    Max number of messages
        language: Filter by language ('english', 'hindi', 'hinglish')
    """
    with get_connection() as conn:
        if language:
            rows = conn.execute("""
                SELECT * FROM messages
                WHERE language = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (language, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM messages
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,)).fetchall()

    return [dict(r) for r in rows]


def get_messages_by_session(session_id: str) -> list[dict]:
    """Fetch all messages from a specific session."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM messages
            WHERE session_id = ?
            ORDER BY timestamp ASC
        """, (session_id,)).fetchall()
    return [dict(r) for r in rows]


def get_opinions(limit: int = 100) -> list[dict]:
    """
    Fetch messages flagged as opinions/beliefs.
    Used by the belief index in Phase 2.
    """
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM messages
            WHERE is_opinion = 1
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_messages_since(since_iso: str, limit: int = 500) -> list[dict]:
    """
    Fetch messages since a given ISO timestamp.
    Used by the weekly summariser in Phase 2.
    """
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM messages
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
            LIMIT ?
        """, (since_iso, limit)).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_stats() -> dict:
    """Return a summary of everything stored so far."""
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        by_lang = conn.execute("""
            SELECT language, COUNT(*) as count
            FROM messages GROUP BY language
        """).fetchall()
        opinions = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE is_opinion = 1"
        ).fetchone()[0]
        sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        oldest = conn.execute(
            "SELECT MIN(timestamp) FROM messages"
        ).fetchone()[0]
        newest = conn.execute(
            "SELECT MAX(timestamp) FROM messages"
        ).fetchone()[0]

    return {
        "total_messages":  total,
        "total_opinions":  opinions,
        "total_sessions":  sessions,
        "by_language":     {r["language"]: r["count"] for r in by_lang},
        "oldest_message":  oldest,
        "newest_message":  newest,
        "db_path":         DB_PATH,
    }


def delete_all(confirm: bool = False):
    """
    Wipe all data. Must pass confirm=True explicitly.
    Used for testing only.
    """
    if not confirm:
        raise ValueError("Pass confirm=True to delete all data.")
    with get_connection() as conn:
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM sessions")
    print("[Storage] All data deleted.")


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from backend.ingest.preprocessor import preprocess

    init_db()

    test_messages = [
        "I believe that waking up early sets the tone for the entire day.",
        "yaar aaj ka din bahut hectic tha, par kaam ho gaya",
        "मुझे लगता है कि परिवार से बड़ा कोई सहारा नहीं होता",
        "Finished reading Atomic Habits today — the 1% improvement idea really stuck with me.",
        "I believe that waking up early sets the tone for the entire day.",   # duplicate
    ]

    print("=== Storage Test ===\n")
    for text in test_messages:
        msg = preprocess(text)
        save_message(msg)

    print("\n--- Stats ---")
    stats = get_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print("\n--- Recent messages ---")
    for m in get_recent_messages(limit=5):
        print(f"  [{m['language']}] {m['text'][:70]}")

    print("\n--- Opinions ---")
    for m in get_opinions():
        print(f"  {m['text'][:70]}")