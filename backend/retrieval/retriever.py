"""
retriever.py — Memory retrieval pipeline
Phase 3: Retrieval & Reasoning Layer

Given a question, this module finds the most relevant memories from
all three sources:
    1. Raw messages     (ChromaDB 'memories' collection)
    2. Weekly summaries (ChromaDB 'summaries' collection)
    3. Belief index     (SQLite beliefs table)

Then combines and deduplicates them into a single ranked context
list ready to be injected into the LLM prompt.
"""

import re
from typing import Optional

from backend.memory.store import search_memories, _search_collection
from backend.memory.belief_index import get_beliefs_by_topic


# ---------------------------------------------------------------------------
# Context item — unified format for all memory types
# ---------------------------------------------------------------------------

class ContextItem:
    def __init__(self, text, source, relevance_score,
                 timestamp=None, language=None, metadata=None):
        self.text            = text
        self.source          = source
        self.relevance_score = relevance_score
        self.timestamp       = timestamp
        self.language        = language
        self.metadata        = metadata or {}

    def to_prompt_line(self) -> str:
        ts   = self.timestamp[:10] if self.timestamp else "unknown date"
        lang = (self.language or "en")[:2].upper()
        return f"[{self.source.upper()} | {ts} | {lang}] {self.text}"

    def __repr__(self):
        return f"<ContextItem source={self.source} score={self.relevance_score:.2f} text={self.text[:50]}>"


# ---------------------------------------------------------------------------
# Topic extraction
# ---------------------------------------------------------------------------

STOP_WORDS = {
    "what", "do", "i", "think", "about", "how", "feel", "is", "my",
    "me", "the", "a", "an", "of", "in", "on", "at", "to", "for",
    "with", "are", "was", "were", "have", "has", "had", "would",
    "should", "could", "will", "can", "did", "does", "it", "that",
    "this", "these", "those", "am", "be", "been", "being",
    "kya", "main", "mein", "se", "ka", "ki", "ke", "ko", "hai",
    "hain", "tha", "thi", "mere", "mera", "meri", "aap", "tum",
}


def extract_query_topics(query: str) -> list:
    words  = re.findall(r'\b[a-zA-Z]{3,}\b', query.lower())
    topics = [w for w in words if w not in STOP_WORDS]
    return list(dict.fromkeys(topics))


# ---------------------------------------------------------------------------
# Core retriever
# ---------------------------------------------------------------------------

def retrieve(
    query,
    top_k_memories  = 6,
    top_k_summaries = 2,
    top_k_beliefs   = 3,
    min_relevance   = 0.25,
    language        = None,
) -> list:
    """
    Retrieve ranked context items from all three memory sources.

    Returns list of ContextItem sorted by relevance.
    """
    context_items = []

    # 1. Raw memories
    try:
        for r in search_memories(query, top_k=top_k_memories, language=language):
            if r["relevance_score"] >= min_relevance:
                context_items.append(ContextItem(
                    text            = r["text"],
                    source          = "memory",
                    relevance_score = r["relevance_score"],
                    timestamp       = r["metadata"].get("timestamp"),
                    language        = r["metadata"].get("language"),
                    metadata        = r["metadata"],
                ))
    except Exception as e:
        print(f"[Retriever] Memory search error: {e}")

    # 2. Weekly summaries
    try:
        for r in _search_collection("summaries", query, top_k_summaries):
            if r["relevance_score"] >= min_relevance:
                context_items.append(ContextItem(
                    text            = r["text"],
                    source          = "summary",
                    relevance_score = r["relevance_score"] * 0.9,
                    timestamp       = r["metadata"].get("period_end"),
                    language        = r["metadata"].get("dominant_lang", "english"),
                    metadata        = r["metadata"],
                ))
    except Exception as e:
        print(f"[Retriever] Summary search error: {e}")

    # 3. Belief index
    try:
        seen_beliefs = set()
        for topic in extract_query_topics(query)[:4]:
            for b in get_beliefs_by_topic(topic)[:top_k_beliefs]:
                if b["id"] not in seen_beliefs:
                    seen_beliefs.add(b["id"])
                    belief_relevance = min(0.85, 0.5 + b["confidence"] * 0.4)
                    context_items.append(ContextItem(
                        text            = b["belief_text"],
                        source          = "belief",
                        relevance_score = belief_relevance,
                        timestamp       = b["last_seen"],
                        language        = b["language"],
                        metadata        = {
                            "topic":         b["topic"],
                            "confidence":    b["confidence"],
                            "mention_count": b["mention_count"],
                        },
                    ))
    except Exception as e:
        print(f"[Retriever] Belief retrieval error: {e}")

    # Deduplicate
    seen_texts  = set()
    deduplicated = []
    for item in context_items:
        fp = item.text[:80].lower().strip()
        if fp not in seen_texts:
            seen_texts.add(fp)
            deduplicated.append(item)

    deduplicated.sort(key=lambda x: x.relevance_score, reverse=True)
    return deduplicated


def retrieve_for_prompt(query, language=None, max_items=10):
    """
    Retrieve context and return (items_list, formatted_string).
    The formatted string is ready to inject into the LLM prompt.
    """
    items     = retrieve(query, language=language)[:max_items]
    formatted = "\n".join(item.to_prompt_line() for item in items)
    return items, formatted


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    queries = [
        "What do I think about waking up early?",
        "How do I feel about my family?",
        "meri productivity ke baare mein kya hai",
    ]
    print("=== Retriever Test ===\n")
    for q in queries:
        print(f"Query: {q}")
        items, formatted = retrieve_for_prompt(q)
        print(formatted if formatted else "  No memories found.")
        print("-" * 60)