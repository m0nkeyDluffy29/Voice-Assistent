"""
store.py — ChromaDB vector database for semantic memory
Phase 2: Memory Layer

Converts every saved message into a vector embedding and stores it
in ChromaDB so that queries can find relevant memories by MEANING,
not just keyword matching.

Example:
    You saved: "I hate waking up late, it ruins my whole day"
    You ask:   "What do I think about mornings?"
    → This finds that message because the meaning is related,
      even though the words 'morning' never appeared.

All data stays on-device in data/chroma_db/
"""

import os
import json
from datetime import datetime, timezone
from typing import Optional

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR    = os.path.join(os.path.dirname(__file__), "../../data/chroma_db")
MODEL_DIR   = os.path.join(os.path.dirname(__file__), "../../models/embeddings")

# ---------------------------------------------------------------------------
# Embedding model (downloads once, cached locally)
# paraphrase-multilingual-MiniLM-L12-v2:
#   - Supports English, Hindi, and 50+ other languages
#   - Small (~120 MB), fast on CPU
#   - Good semantic similarity for short to medium texts
# ---------------------------------------------------------------------------

_embed_model: Optional[SentenceTransformer] = None

def get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        os.makedirs(MODEL_DIR, exist_ok=True)
        print("[Store] Loading embedding model (first load may take a moment)...")
        _embed_model = SentenceTransformer(
            "paraphrase-multilingual-MiniLM-L12-v2",
            cache_folder=MODEL_DIR
        )
        print("[Store] Embedding model ready.")
    return _embed_model


def embed(text: str) -> list[float]:
    """Convert a text string into a vector embedding."""
    model = get_embed_model()
    return model.encode(text, normalize_embeddings=True).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts at once (faster than one-by-one)."""
    model = get_embed_model()
    return model.encode(texts, normalize_embeddings=True).tolist()


# ---------------------------------------------------------------------------
# ChromaDB client + collections
# ---------------------------------------------------------------------------

_client: Optional[chromadb.PersistentClient] = None

def get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        os.makedirs(BASE_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=BASE_DIR,
            settings=Settings(anonymized_telemetry=False)
        )
    return _client


def get_collection(name: str = "memories") -> chromadb.Collection:
    """
    Get or create a ChromaDB collection.

    Collections:
        memories    — all messages (main search target)
        opinions    — only opinion/belief messages (for belief index)
        summaries   — weekly summary documents
    """
    client = get_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"}   # cosine similarity for semantic search
    )


# ---------------------------------------------------------------------------
# Write — add memory to vector store
# ---------------------------------------------------------------------------

def add_memory(message: dict) -> bool:
    """
    Embed a preprocessed message and add it to ChromaDB.

    Args:
        message: dict from preprocessor.preprocess() — must have been
                 saved to SQLite first (storage.save_message)

    Returns:
        True if added, False if already exists
    """
    collection = get_collection("memories")

    # Skip if already embedded (idempotent)
    existing = collection.get(ids=[message["id"]])
    if existing["ids"]:
        print(f"[Store] Already embedded: {message['id'][:8]}...")
        return False

    vector = embed(message["text"])

    # Metadata stored alongside the vector (used for filtering + display)
    metadata = {
        "language":   message["language"],
        "source":     message["source"],
        "is_opinion": int(message["entities"].get("is_opinion", False)),
        "timestamp":  message["timestamp"],
        "session_id": message["session_id"],
        "word_count": message["word_count"],
    }

    collection.add(
        ids        = [message["id"]],
        embeddings = [vector],
        documents  = [message["text"]],
        metadatas  = [metadata],
    )

    # Also add to opinions collection if flagged
    if message["entities"].get("is_opinion"):
        op_collection = get_collection("opinions")
        op_collection.add(
            ids        = [message["id"]],
            embeddings = [vector],
            documents  = [message["text"]],
            metadatas  = [metadata],
        )

    print(f"[Store] Embedded message {message['id'][:8]}... ({message['language']})")
    return True


def add_summary(summary_id: str, text: str, metadata: dict) -> bool:
    """
    Add a weekly summary document to the summaries collection.
    Called by summariser.py after generating a digest.
    """
    collection = get_collection("summaries")
    existing = collection.get(ids=[summary_id])
    if existing["ids"]:
        return False

    vector = embed(text)
    collection.add(
        ids        = [summary_id],
        embeddings = [vector],
        documents  = [text],
        metadatas  = [metadata],
    )
    print(f"[Store] Summary embedded: {summary_id[:8]}...")
    return True


# ---------------------------------------------------------------------------
# Read — semantic search
# ---------------------------------------------------------------------------

def search_memories(
    query: str,
    top_k: int = 7,
    language: str = None,
    opinions_only: bool = False,
) -> list[dict]:
    """
    Find the most semantically relevant memories for a query.

    Args:
        query:         The question or topic to search for
        top_k:         Number of results to return
        language:      Filter to a specific language ('english', 'hindi', 'hinglish')
        opinions_only: Search only opinion/belief messages

    Returns:
        List of dicts with keys: id, text, metadata, distance, relevance_score
        Sorted by relevance (highest first).
    """
    collection_name = "opinions" if opinions_only else "memories"
    collection = get_collection(collection_name)

    # Check collection has data
    count = collection.count()
    if count == 0:
        print(f"[Store] Collection '{collection_name}' is empty — nothing to search yet.")
        return []

    query_vector = embed(query)

    # Build optional where filter
    where = None
    if language:
        where = {"language": {"$eq": language}}

    results = collection.query(
        query_embeddings = [query_vector],
        n_results        = min(top_k, count),
        where            = where,
        include          = ["documents", "metadatas", "distances"],
    )

    # Reformat results into clean dicts
    output = []
    for i, doc_id in enumerate(results["ids"][0]):
        distance = results["distances"][0][i]
        # ChromaDB cosine distance: 0 = identical, 2 = opposite
        # Convert to a 0-1 relevance score
        relevance = max(0.0, 1.0 - (distance / 2.0))

        output.append({
            "id":             doc_id,
            "text":           results["documents"][0][i],
            "metadata":       results["metadatas"][0][i],
            "distance":       round(distance, 4),
            "relevance_score": round(relevance, 4),
        })

    # Sort by relevance descending
    output.sort(key=lambda x: x["relevance_score"], reverse=True)
    return output


def search_summaries(query: str, top_k: int = 3) -> list[dict]:
    """Search weekly summaries by semantic similarity."""
    return search_memories.__wrapped__(
        query, top_k, collection_name="summaries"
    ) if hasattr(search_memories, "__wrapped__") else _search_collection("summaries", query, top_k)


def _search_collection(collection_name: str, query: str, top_k: int) -> list[dict]:
    collection = get_collection(collection_name)
    count = collection.count()
    if count == 0:
        return []
    query_vector = embed(query)
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=min(top_k, count),
        include=["documents", "metadatas", "distances"],
    )
    output = []
    for i, doc_id in enumerate(results["ids"][0]):
        distance = results["distances"][0][i]
        relevance = max(0.0, 1.0 - (distance / 2.0))
        output.append({
            "id": doc_id,
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "relevance_score": round(relevance, 4),
        })
    return sorted(output, key=lambda x: x["relevance_score"], reverse=True)


# ---------------------------------------------------------------------------
# Bulk embed — sync SQLite → ChromaDB
# ---------------------------------------------------------------------------

def sync_from_sqlite(messages: list[dict]) -> dict:
    """
    Embed all messages from SQLite that aren't in ChromaDB yet.
    Run this on Phase 2 first launch to backfill existing messages.

    Args:
        messages: list of message dicts from storage.get_recent_messages()

    Returns:
        {"embedded": int, "skipped": int}
    """
    embedded = skipped = 0
    texts    = []
    to_add   = []

    collection = get_collection("memories")

    for msg in messages:
        existing = collection.get(ids=[msg["id"]])
        if existing["ids"]:
            skipped += 1
            continue
        texts.append(msg["text"])
        to_add.append(msg)

    if not to_add:
        print(f"[Store] Sync complete — all {skipped} messages already embedded.")
        return {"embedded": 0, "skipped": skipped}

    print(f"[Store] Embedding {len(to_add)} messages in batch...")
    vectors = embed_batch(texts)

    for msg, vector in zip(to_add, vectors):
        metadata = {
            "language":   msg["language"],
            "source":     msg["source"],
            "is_opinion": int(json.loads(msg.get("entities_json", "{}")).get("is_opinion", False)),
            "timestamp":  msg["timestamp"],
            "session_id": msg["session_id"],
            "word_count": msg["word_count"],
        }
        collection.add(
            ids        = [msg["id"]],
            embeddings = [vector],
            documents  = [msg["text"]],
            metadatas  = [metadata],
        )
        embedded += 1

    print(f"[Store] Sync done — {embedded} embedded, {skipped} already existed.")
    return {"embedded": embedded, "skipped": skipped}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_store_stats() -> dict:
    memories  = get_collection("memories").count()
    opinions  = get_collection("opinions").count()
    summaries = get_collection("summaries").count()
    return {
        "total_memories_embedded": memories,
        "total_opinions_embedded": opinions,
        "total_summaries":         summaries,
        "chroma_db_path":          BASE_DIR,
    }


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Vector Store Test ===\n")

    test_messages = [
        {
            "id": "test-001", "text": "I believe discipline is more important than motivation",
            "language": "english", "source": "text", "session_id": "s1",
            "word_count": 9, "timestamp": datetime.now(timezone.utc).isoformat(),
            "entities": {"is_opinion": True, "dates": [], "numbers": []}
        },
        {
            "id": "test-002", "text": "yaar mujhe lagta hai consistency se hi kuch banta hai",
            "language": "hinglish", "source": "text", "session_id": "s1",
            "word_count": 10, "timestamp": datetime.now(timezone.utc).isoformat(),
            "entities": {"is_opinion": True, "dates": [], "numbers": []}
        },
        {
            "id": "test-003", "text": "Had a really productive morning today, finished 3 tasks before 10am",
            "language": "english", "source": "text", "session_id": "s1",
            "word_count": 12, "timestamp": datetime.now(timezone.utc).isoformat(),
            "entities": {"is_opinion": False, "dates": [], "numbers": ["3", "10"]}
        },
    ]

    for msg in test_messages:
        add_memory(msg)

    print("\n--- Searching: 'what do I think about habits and consistency' ---")
    results = search_memories("what do I think about habits and consistency", top_k=3)
    for r in results:
        print(f"  [{r['relevance_score']:.2f}] {r['text']}")

    print("\n--- Stats ---")
    stats = get_store_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")