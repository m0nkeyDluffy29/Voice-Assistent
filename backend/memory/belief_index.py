"""
belief_index.py — Opinion and belief tracker
Phase 2: Memory Layer

Scans all messages flagged as opinions (is_opinion=True) and builds a
structured index of the person's recurring beliefs, values, and patterns.

This is what makes the agent feel like YOU — not just a search engine
over your notes, but something that understands your worldview.

Stored in: data/raw_logs/conversations.db (beliefs table)
Also embedded in ChromaDB 'opinions' collection for semantic retrieval.
"""

import os
import json
import uuid
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager
from collections import defaultdict

import ollama

# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------

DB_DIR  = os.path.join(os.path.dirname(__file__), "../../data/raw_logs")
DB_PATH = os.path.join(DB_DIR, "conversations.db")


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


def init_beliefs_table():
    """Create the beliefs table if it doesn't exist."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS beliefs (
                id              TEXT PRIMARY KEY,
                topic           TEXT NOT NULL,
                belief_text     TEXT NOT NULL,
                source_ids      TEXT NOT NULL DEFAULT '[]',
                confidence      REAL NOT NULL DEFAULT 0.5,
                language        TEXT NOT NULL DEFAULT 'english',
                first_seen      TEXT NOT NULL,
                last_seen       TEXT NOT NULL,
                mention_count   INTEGER NOT NULL DEFAULT 1,
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_beliefs_topic
                ON beliefs(topic);

            CREATE INDEX IF NOT EXISTS idx_beliefs_confidence
                ON beliefs(confidence DESC);
        """)


# ---------------------------------------------------------------------------
# Extraction prompts
# ---------------------------------------------------------------------------

BELIEF_EXTRACT_PROMPT = """You are analysing someone's personal notes to extract their core beliefs.

Below are messages where the person expressed opinions, values, or strong views.
Extract distinct beliefs as a JSON array. Each belief should have:
- "topic": 2-4 word category (e.g. "morning routines", "work ethic", "family")
- "belief": one clear sentence stating what the person believes
- "confidence": 0.0 to 1.0 (how strongly stated — 1.0 = very definitive)

Return ONLY the JSON array, no explanation, no markdown fences.

Messages:
{messages}

JSON:"""


CLUSTER_PROMPT = """Below are two belief statements. Do they express the SAME core belief?
Reply with only "yes" or "no".

Belief 1: {b1}
Belief 2: {b2}"""


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def _call_llm(prompt: str, model: str = "mistral") -> str:
    try:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2}
        )
        return response["message"]["content"].strip()
    except Exception as e:
        print(f"[BeliefIndex] LLM error: {e}")
        raise


def extract_beliefs_from_messages(
    messages: list[dict],
    model: str = "mistral",
    batch_size: int = 20,
) -> list[dict]:
    """
    Extract structured beliefs from a list of opinion messages.

    Args:
        messages:   Opinion messages (is_opinion=True) from storage.get_opinions()
        model:      Ollama model
        batch_size: Process this many messages per LLM call

    Returns:
        List of raw belief dicts: [{topic, belief, confidence, source_ids}]
    """
    if not messages:
        return []

    all_beliefs = []

    for i in range(0, len(messages), batch_size):
        batch = messages[i : i + batch_size]
        joined = "\n---\n".join(
            f"[{m['language']}] {m['text']}" for m in batch
        )
        source_ids = [m["id"] for m in batch]

        prompt = BELIEF_EXTRACT_PROMPT.format(messages=joined)

        try:
            raw = _call_llm(prompt, model)
            raw = raw.replace("```json", "").replace("```", "").strip()
            extracted = json.loads(raw)

            for b in extracted:
                if isinstance(b, dict) and "topic" in b and "belief" in b:
                    all_beliefs.append({
                        "topic":      b.get("topic", "general").lower().strip(),
                        "belief":     b.get("belief", "").strip(),
                        "confidence": float(b.get("confidence", 0.5)),
                        "source_ids": source_ids,
                    })

        except (json.JSONDecodeError, Exception) as e:
            print(f"[BeliefIndex] Batch {i//batch_size + 1} extraction failed: {e}")
            continue

    return all_beliefs


def _are_same_belief(b1: str, b2: str, model: str = "mistral") -> bool:
    """Check if two belief statements say the same thing."""
    try:
        prompt = CLUSTER_PROMPT.format(b1=b1, b2=b2)
        response = _call_llm(prompt, model).lower()
        return response.startswith("yes")
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Belief index builder
# ---------------------------------------------------------------------------

def build_belief_index(model: str = "mistral") -> dict:
    """
    Full pipeline:
    1. Pull all opinion messages from SQLite
    2. Extract beliefs via LLM
    3. Merge duplicates
    4. Save/update the beliefs table

    Returns:
        {"new": int, "updated": int, "total": int}
    """
    init_beliefs_table()

    from backend.ingest.storage import get_opinions
    opinion_messages = get_opinions(limit=500)

    if not opinion_messages:
        print("[BeliefIndex] No opinion messages found. Talk to the agent more first.")
        return {"new": 0, "updated": 0, "total": 0}

    print(f"[BeliefIndex] Processing {len(opinion_messages)} opinion messages...")
    raw_beliefs = extract_beliefs_from_messages(opinion_messages, model)

    if not raw_beliefs:
        print("[BeliefIndex] No beliefs extracted.")
        return {"new": 0, "updated": 0, "total": 0}

    print(f"[BeliefIndex] Extracted {len(raw_beliefs)} raw beliefs. Merging...")

    new_count = updated_count = 0
    now = datetime.now(timezone.utc).isoformat()

    for raw in raw_beliefs:
        topic   = raw["topic"]
        belief  = raw["belief"]
        sources = raw["source_ids"]
        conf    = raw["confidence"]

        # Check if a similar belief already exists for this topic
        with get_connection() as conn:
            existing_rows = conn.execute("""
                SELECT id, belief_text, source_ids, mention_count, confidence
                FROM beliefs WHERE topic = ?
            """, (topic,)).fetchall()

        matched = None
        for row in existing_rows:
            if _are_same_belief(belief, row["belief_text"], model):
                matched = dict(row)
                break

        if matched:
            # Update existing belief
            merged_sources = list(set(
                json.loads(matched["source_ids"]) + sources
            ))
            new_conf = round(
                (matched["confidence"] * matched["mention_count"] + conf) /
                (matched["mention_count"] + 1),
                3
            )
            with get_connection() as conn:
                conn.execute("""
                    UPDATE beliefs SET
                        source_ids    = ?,
                        confidence    = ?,
                        mention_count = mention_count + 1,
                        last_seen     = ?,
                        updated_at    = ?
                    WHERE id = ?
                """, (
                    json.dumps(merged_sources),
                    new_conf,
                    now,
                    now,
                    matched["id"],
                ))
            updated_count += 1

        else:
            # Insert new belief
            # Guess language from source messages
            lang = "english"
            for m in opinion_messages:
                if m["id"] in sources:
                    lang = m["language"]
                    break

            with get_connection() as conn:
                conn.execute("""
                    INSERT INTO beliefs
                        (id, topic, belief_text, source_ids, confidence,
                         language, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()),
                    topic,
                    belief,
                    json.dumps(sources),
                    conf,
                    lang,
                    now,
                    now,
                ))
            new_count += 1

    total = get_belief_count()
    print(f"[BeliefIndex] Done — {new_count} new, {updated_count} updated, {total} total beliefs.")
    return {"new": new_count, "updated": updated_count, "total": total}


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def get_beliefs_by_topic(topic: str) -> list[dict]:
    """Get all beliefs about a specific topic."""
    init_beliefs_table()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM beliefs
            WHERE topic LIKE ?
            ORDER BY confidence DESC
        """, (f"%{topic}%",)).fetchall()
    return [dict(r) for r in rows]


def get_top_beliefs(limit: int = 20) -> list[dict]:
    """Get the most confidently held beliefs."""
    init_beliefs_table()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM beliefs
            ORDER BY confidence DESC, mention_count DESC
            LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_all_topics() -> list[str]:
    """Get all belief topics."""
    init_beliefs_table()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT topic FROM beliefs ORDER BY topic"
        ).fetchall()
    return [r["topic"] for r in rows]


def get_belief_count() -> int:
    init_beliefs_table()
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM beliefs").fetchone()[0]


def get_belief_summary() -> str:
    """
    Return a compact text summary of all beliefs.
    Injected into the LLM prompt in Phase 3 so it knows your worldview.
    """
    beliefs = get_top_beliefs(limit=30)
    if not beliefs:
        return "No beliefs recorded yet."

    lines = []
    by_topic = defaultdict(list)
    for b in beliefs:
        by_topic[b["topic"]].append(b["belief_text"])

    for topic, items in by_topic.items():
        lines.append(f"\n[{topic.upper()}]")
        for item in items[:3]:   # Max 3 beliefs per topic
            lines.append(f"  • {item}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Belief Index Test ===\n")
    result = build_belief_index()
    print(f"\nResult: {result}")

    print("\n--- Top Beliefs ---")
    for b in get_top_beliefs(limit=5):
        print(f"  [{b['topic']}] (conf: {b['confidence']}) {b['belief_text']}")

    print("\n--- All Topics ---")
    print(", ".join(get_all_topics()))

    print("\n--- Belief Summary ---")
    print(get_belief_summary())