"""
preprocessor.py — Message cleaning, tagging, and deduplication
Phase 1: Data Ingestion Layer

Takes raw text (typed or transcribed) and returns a clean, enriched
dict ready to be stored in the database.

Output format:
    {
        "id":          str   — unique message ID
        "text":        str   — cleaned text
        "raw_text":    str   — original unmodified text
        "language":    str   — 'english' | 'hindi' | 'hinglish'
        "entities":    dict  — extracted dates, numbers, opinion flag
        "source":      str   — 'text' | 'voice'
        "timestamp":   str   — ISO 8601
        "session_id":  str   — groups messages from the same sitting
        "word_count":  int
        "is_duplicate": bool
    }
"""

import re
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Literal

from backend.ingest.language_utils import (
    detect_language,
    preprocess_text,
    extract_entities,
    Language,
)

# ---------------------------------------------------------------------------
# Session tracking (groups messages recorded close in time)
# ---------------------------------------------------------------------------

_current_session_id: str = str(uuid.uuid4())
_session_start: datetime = datetime.now(timezone.utc)
SESSION_TIMEOUT_MINUTES = 30    # New session if gap > 30 min


def get_or_create_session() -> str:
    """Return current session ID, rotating if idle for too long."""
    global _current_session_id, _session_start
    now = datetime.now(timezone.utc)
    elapsed = (now - _session_start).total_seconds() / 60

    if elapsed > SESSION_TIMEOUT_MINUTES:
        _current_session_id = str(uuid.uuid4())
        _session_start = now

    return _current_session_id


# ---------------------------------------------------------------------------
# Deduplication fingerprint
# ---------------------------------------------------------------------------

def _fingerprint(text: str) -> str:
    """
    Create a short fingerprint for near-duplicate detection.
    Strips punctuation and whitespace before hashing so that
    "I think so." and "i think so" get the same fingerprint.
    """
    cleaned = re.sub(r'[^\w\s]', '', text.lower())
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return hashlib.md5(cleaned.encode()).hexdigest()


# In-memory seen fingerprints for the current run (across restarts,
# duplicates are checked against the DB in storage.py).
_seen_fingerprints: set[str] = set()


def is_duplicate(text: str) -> bool:
    """
    Check if this exact (or near-exact) message was already processed
    in the current session. Does not check the database — that's done
    in storage.py before the final write.
    """
    fp = _fingerprint(text)
    if fp in _seen_fingerprints:
        return True
    _seen_fingerprints.add(fp)
    return False


# ---------------------------------------------------------------------------
# Core preprocessor
# ---------------------------------------------------------------------------

def preprocess(
    raw_text: str,
    source: Literal["text", "voice"] = "text",
    force_language: Language = None,
) -> dict:
    """
    Clean and enrich a raw message.

    Args:
        raw_text:       The original text (typed or from Whisper)
        source:         'text' (user typed) or 'voice' (from microphone)
        force_language: Override auto-detection if you already know the lang

    Returns:
        Enriched message dict ready for storage.
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("Cannot preprocess empty text.")

    raw_text = raw_text.strip()

    # --- Language detection ---
    language = force_language or detect_language(raw_text)

    # --- Text cleaning ---
    clean_text = preprocess_text(raw_text, language)

    # --- Entity extraction ---
    entities = extract_entities(clean_text)

    # --- Duplicate check ---
    duplicate = is_duplicate(clean_text)

    # --- Build the enriched message ---
    message = {
        "id":           str(uuid.uuid4()),
        "text":         clean_text,
        "raw_text":     raw_text,
        "language":     language,
        "entities":     entities,
        "source":       source,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "session_id":   get_or_create_session(),
        "word_count":   len(clean_text.split()),
        "is_duplicate": duplicate,
        "fingerprint":  _fingerprint(clean_text),
    }

    return message


def preprocess_batch(texts: list[str], source: str = "text") -> list[dict]:
    """
    Preprocess multiple messages at once.
    Useful for importing existing notes or chat logs.
    """
    results = []
    for text in texts:
        try:
            msg = preprocess(text, source=source)
            results.append(msg)
        except ValueError:
            continue    # Skip empty strings
    return results


# ---------------------------------------------------------------------------
# Pretty printer for debugging
# ---------------------------------------------------------------------------

def describe(message: dict) -> str:
    """Return a human-readable summary of a preprocessed message."""
    lines = [
        f"ID:        {message['id'][:8]}...",
        f"Language:  {message['language']}",
        f"Source:    {message['source']}",
        f"Words:     {message['word_count']}",
        f"Opinion:   {message['entities']['is_opinion']}",
        f"Duplicate: {message['is_duplicate']}",
        f"Time:      {message['timestamp']}",
        f"Text:      {message['text'][:120]}{'...' if len(message['text']) > 120 else ''}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_inputs = [
        ("I believe consistency is more important than intensity when building habits.", "text"),
        ("yaar mujhe lagta hai ki discipline bahut zaroor hai zindagi mein", "text"),
        ("मुझे लगता है कि परिवार सबसे जरूरी चीज़ है", "text"),
        ("Today I had a meeting at 10am and it went really well.", "voice"),
        ("I believe consistency is more important than intensity when building habits.", "text"),  # duplicate
    ]

    print("=== Preprocessor Test ===\n")
    for raw, source in test_inputs:
        msg = preprocess(raw, source=source)
        print(describe(msg))
        print("-" * 60)