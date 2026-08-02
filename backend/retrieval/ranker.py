"""
ranker.py — Re-rank retrieved context by recency + relevance
Phase 3: Retrieval & Reasoning Layer

After retriever.py pulls the raw candidates, ranker.py applies a
combined score so that:
  - Very recent memories rank higher (you've been thinking about this)
  - High relevance still matters most
  - Beliefs with high confidence get a boost
  - Old but highly relevant memories aren't completely buried

Final score formula:
    score = relevance * 0.65 + recency * 0.25 + source_boost * 0.10
"""

from datetime import datetime, timezone
from backend.retrieval.retriever import ContextItem


# ---------------------------------------------------------------------------
# Recency scoring
# ---------------------------------------------------------------------------

def recency_score(timestamp_iso: str) -> float:
    """
    Convert a timestamp into a 0-1 recency score.

    Decay curve:
        Today       → 1.0
        1 week ago  → 0.85
        1 month ago → 0.60
        3 months    → 0.35
        6 months+   → 0.15
    """
    if not timestamp_iso:
        return 0.3   # Unknown timestamp → neutral score

    try:
        ts  = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_days = max(0, (now - ts).days)
    except (ValueError, TypeError):
        return 0.3

    if age_days == 0:
        return 1.0
    elif age_days <= 7:
        return 0.85
    elif age_days <= 30:
        return 0.70
    elif age_days <= 90:
        return 0.50
    elif age_days <= 180:
        return 0.30
    else:
        return 0.15


# ---------------------------------------------------------------------------
# Source boost
# ---------------------------------------------------------------------------

SOURCE_BOOST = {
    "belief":  1.0,    # Beliefs are your most distilled thoughts
    "memory":  0.85,   # Raw memories are direct
    "summary": 0.70,   # Summaries are processed/compressed
}


# ---------------------------------------------------------------------------
# Core ranker
# ---------------------------------------------------------------------------

def rank(items: list, query: str = "") -> list:
    """
    Re-rank a list of ContextItems using combined score.

    Args:
        items: list of ContextItem from retriever.retrieve()
        query: original query (reserved for future query-aware boosting)

    Returns:
        New list of ContextItem sorted by final_score descending.
        Each item gets a .final_score attribute added.
    """
    for item in items:
        r  = item.relevance_score
        rc = recency_score(item.timestamp)
        sb = SOURCE_BOOST.get(item.source, 0.75)

        item.final_score = round(r * 0.65 + rc * 0.25 + sb * 0.10, 4)

        # Extra boost for high-confidence beliefs mentioned many times
        if item.source == "belief":
            confidence    = item.metadata.get("confidence", 0.5)
            mention_count = item.metadata.get("mention_count", 1)
            repeat_boost  = min(0.05, (mention_count - 1) * 0.01)
            item.final_score = min(1.0, item.final_score + confidence * 0.05 + repeat_boost)

    return sorted(items, key=lambda x: x.final_score, reverse=True)


def rank_and_trim(items: list, query: str = "", max_tokens: int = 1800) -> list:
    """
    Rank items and then trim to fit within an approximate token budget.
    Rough estimate: 1 token ≈ 4 characters.
    """
    if not items:
        return []

    ranked      = rank(items, query)
    selected    = []
    char_budget = max_tokens * 4
    used_chars  = 0

    for item in ranked:
        try:
            line_len = len(item.to_prompt_line()) + 1
        except Exception:
            continue
        if used_chars + line_len > char_budget:
            break
        selected.append(item)
        used_chars += line_len

    return selected


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from backend.retrieval.retriever import retrieve

    query = "What do I think about mornings and discipline?"
    print(f"=== Ranker Test ===\nQuery: {query}\n")

    items  = retrieve(query)
    ranked = rank(items, query)

    for i, item in enumerate(ranked, 1):
        print(f"{i}. [{item.source}] score={item.final_score:.3f}")
        print(f"   {item.text[:100]}")