from datetime import datetime, timezone
from backend.retrieval.retriever import ContextItem

def recency_score(timestamp_iso: str) -> float:
  if not timestamp_iso:
    return 0.3

  try:
    ts = datetime.fromisocalendar(timestamp_iso.replace("Z", "+00:00"))
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

SOURCE_BOOST = {
  "belief": 1.0,
  "memory": 0.85,
  "summary": 0.70,
}

def rank(items: list, query: str = "") -> list:
  for item in items:
    r = item.relevance_score
    rc = recency_score(item.timestamp)
    sb = SOURCE_BOOST.get(item.source, 0.75)

    item.final_score = round(r * 0.65 + rc * 0.25 + sb * 0.10, 4)

    if item.source == "belief":
      confidence = item.metadata.get("confidence", 0.5)
      mention_count = item.metadata.get("mention_count", 1)
      repeat_boost = min(0.05, (mention_count - 1) * 0.01)
      item.final_score = min(1.0, item.final_score + confidence * 0.05 + repeat_boost)
  return sorted(items, key=lambda x: x.final_score, reverse=True)

def rank_and_trim(items: list, query: str = "", max_tokens: int = 1800) -> list:
  ranked = rank(items, query)
  selected = []
  char_budget = max_tokens * 4
  used_char = 0

  for item in ranked:
    line_len = len(item.to_prompt_line()) + 1
    if used_char + line_len > char_budget:
      break
    selected.append(item)
    used_chars += line_len

  return selected 

if __name__ == "__main__":
  from backend.retrieval.retriever import retrieve

  query = "What do I think about mornings and discipline?"
  print(f"=== Ranker Test ===\nQuery: {query}\n")

  items = retrieve(query)
  ranked = rank(items, query)
  for i, item in enumerate(ranked, 1):
    print(f"{i}. [{item.source}] score={item.final_score:.3f}")
    print(f"{item.text[:100]}")
