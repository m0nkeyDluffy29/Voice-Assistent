"""
main.py — Daily conversation interface
Personal AI Agent — Phase 1 + Phase 2

Run this every day to feed data to your agent.

Usage:
    python main.py                  # Start the daily conversation (text mode)
    python main.py --voice          # Start with voice input (microphone)
    python main.py --stats          # Show memory + vector store stats
    python main.py --import notes.txt   # Import text from a file
    python main.py --sync           # Backfill existing messages into ChromaDB
    python main.py --summarise      # Generate this week's memory summary
    python main.py --beliefs        # Build / update your belief index
    python main.py --search "query" # Search your memories semantically
"""

import argparse
import sys
import os

# Make sure backend is importable
sys.path.insert(0, os.path.dirname(__file__))

from backend.ingest.storage import init_db, save_message, get_stats, get_recent_messages
from backend.ingest.preprocessor import preprocess
from backend.ingest.listener import record_and_transcribe, MicRecorder, transcribe_file
from backend.ingest.language_utils import detect_language


# ---------------------------------------------------------------------------
# Session welcome
# ---------------------------------------------------------------------------

BANNER = """
╔══════════════════════════════════════════════════════╗
║           🧠  Your Personal AI Agent                 ║
║           Talk to it daily. It remembers.            ║
╚══════════════════════════════════════════════════════╝
"""

HELP_TEXT = """
Commands (type these at any time):
  /quit or /exit  — end the session
  /stats          — show memory + vector store stats
  /recent         — show your last 5 messages
  /voice          — switch to voice input for one message
  /search <query> — search your memories semantically
  /beliefs        — show your belief index
  /summarise      — generate this week's summary (needs Ollama)
  /help           — show this help

Just type normally to save a thought, opinion, or experience.
Speak in English, Hindi, or Hinglish — it understands all three.
"""


# ---------------------------------------------------------------------------
# Text mode loop
# ---------------------------------------------------------------------------

def text_mode():
    """Interactive text input loop."""
    print(HELP_TEXT)
    session_count = 0

    while True:
        try:
            raw = input("\nYou → ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n[Agent] Session ended. Goodbye!")
            break

        if not raw:
            continue

        # Commands
        if raw.lower() in ("/quit", "/exit", "quit", "exit", "bye"):
            print("\n[Agent] Session ended. See you tomorrow!")
            break

        if raw.lower() == "/help":
            print(HELP_TEXT)
            continue

        if raw.lower() == "/stats":
            print_stats()
            continue

        if raw.lower() == "/recent":
            print_recent()
            continue

        if raw.lower().startswith("/search "):
            query = raw[8:].strip()
            if query:
                run_search(query)
            else:
                print("[Agent] Usage: /search <your question>")
            continue

        if raw.lower() == "/beliefs":
            print_beliefs()
            continue

        if raw.lower() == "/summarise":
            run_summarise()
            continue

        if raw.lower() == "/voice":
            result = record_and_transcribe()
            raw = result["text"]
            if not raw:
                print("[Agent] Couldn't catch that. Try again.")
                continue
            print(f"[Agent] Heard: {raw}")

        # Process and save
        try:
            msg = preprocess(raw, source="text")
            saved = save_message(msg)

            if saved:
                lang_label = {
                    "english": "EN",
                    "hindi": "HI",
                    "hinglish": "HI+EN"
                }.get(msg["language"], "?")

                opinion_tag = " 💭 [opinion noted]" if msg["entities"]["is_opinion"] else ""
                print(f"[Agent] Saved [{lang_label}]{opinion_tag} ✓")
                session_count += 1
            else:
                print("[Agent] Already have that one — not re-saving.")

        except ValueError as e:
            print(f"[Agent] Error: {e}")

    if session_count > 0:
        print(f"\n[Agent] {session_count} new memories added this session.")


# ---------------------------------------------------------------------------
# Voice mode loop
# ---------------------------------------------------------------------------

def voice_mode():
    """Full voice input loop — speak, it transcribes and saves."""
    print("\n[Agent] Voice mode active.")
    print("  Hold Enter to record, release to stop.")
    print("  Type /quit to exit.\n")

    while True:
        cmd = input("Press Enter to speak (or /quit): ").strip().lower()

        if cmd in ("/quit", "quit", "exit"):
            print("[Agent] Session ended.")
            break

        result = record_and_transcribe()
        raw = result["text"]

        if not raw:
            print("[Agent] Nothing captured. Try again.")
            continue

        print(f"[Agent] Heard ({result['language']}): {raw}")

        msg = preprocess(raw, source="voice", force_language=result["language"])
        saved = save_message(msg)

        if saved:
            opinion_tag = " 💭 [opinion noted]" if msg["entities"]["is_opinion"] else ""
            print(f"[Agent] Saved{opinion_tag} ✓")
        else:
            print("[Agent] Already in memory.")


# ---------------------------------------------------------------------------
# Import from file
# ---------------------------------------------------------------------------

def import_file(path: str):
    """
    Import text from a file — one thought per line.
    Useful for importing old journal entries or notes.
    """
    if not os.path.exists(path):
        print(f"[Error] File not found: {path}")
        return

    with open(path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    print(f"[Import] Found {len(lines)} lines in {path}")

    saved = skipped = 0
    for line in lines:
        try:
            msg = preprocess(line, source="text")
            if save_message(msg):
                saved += 1
            else:
                skipped += 1
        except ValueError:
            skipped += 1

    print(f"[Import] Done — {saved} saved, {skipped} skipped.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def print_stats():
    stats = get_stats()
    print("\n📊 Your memory so far:")
    print(f"   Total messages : {stats['total_messages']}")
    print(f"   Opinions saved : {stats['total_opinions']}")
    print(f"   Sessions       : {stats['total_sessions']}")
    print(f"   Languages      : {stats['by_language']}")
    if stats["oldest_message"]:
        print(f"   First entry    : {stats['oldest_message'][:10]}")
    if stats["newest_message"]:
        print(f"   Latest entry   : {stats['newest_message'][:10]}")


def print_recent():
    messages = get_recent_messages(limit=5)
    if not messages:
        print("\n[Agent] No messages yet. Start talking!")
        return
    print("\n📖 Your last 5 entries:")
    for m in messages:
        ts = m["timestamp"][:10]
        lang = m["language"][:2].upper()
        print(f"   [{ts}][{lang}] {m['text'][:80]}")


def run_search(query: str):
    """Phase 2: semantic search over memories."""
    try:
        from backend.memory.store import search_memories
        print(f"\n🔍 Searching memories for: '{query}'")
        results = search_memories(query, top_k=5)
        if not results:
            print("   No relevant memories found yet.")
            return
        for i, r in enumerate(results, 1):
            score = r["relevance_score"]
            lang  = r["metadata"].get("language", "?")[:2].upper()
            ts    = r["metadata"].get("timestamp", "")[:10]
            print(f"\n   {i}. [{score:.0%} match][{lang}][{ts}]")
            print(f"      {r['text'][:120]}")
    except ImportError:
        print("[Agent] Phase 2 not installed. Run: pip install chromadb sentence-transformers")


def print_beliefs():
    """Phase 2: show belief index."""
    try:
        from backend.memory.belief_index import get_top_beliefs, get_all_topics, get_belief_count
        count = get_belief_count()
        if count == 0:
            print("\n[Agent] No beliefs indexed yet. Run /summarise or python main.py --beliefs first.")
            return
        print(f"\n🧭 Your belief index ({count} beliefs):")
        for b in get_top_beliefs(limit=10):
            print(f"   [{b['topic']}] {b['belief_text']}")
            print(f"          confidence: {b['confidence']:.0%}  mentions: {b['mention_count']}")
    except ImportError:
        print("[Agent] Phase 2 not installed. Run: pip install chromadb sentence-transformers ollama")


def run_summarise():
    """Phase 2: generate weekly summary."""
    try:
        from backend.memory.summariser import run_weekly_summary
        print("\n📝 Generating weekly summary (needs Ollama running)...")
        result = run_weekly_summary()
        if result.get("skipped"):
            reason = result.get("reason", "unknown")
            if reason == "already_exists":
                print("[Agent] Summary already exists for this week. Use --force to regenerate.")
            else:
                print(f"[Agent] Skipped: {reason}")
        else:
            print(f"\n--- Summary ---\n{result['summary_text']}")
            if result.get("topics"):
                print(f"\nTopics: {', '.join(result['topics'])}")
    except ImportError:
        print("[Agent] Phase 2 not installed. Run: pip install chromadb sentence-transformers ollama")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Personal AI Agent — Phase 1: Daily conversation"
    )
    parser.add_argument("--voice",     action="store_true", help="Use voice input")
    parser.add_argument("--stats",     action="store_true", help="Show memory stats and exit")
    parser.add_argument("--import",    dest="import_file", metavar="FILE",
                        help="Import thoughts from a text file (one per line)")
    # ── Phase 2 args ─────────────────────────────────────────────────────────
    parser.add_argument("--sync",      action="store_true",
                        help="Backfill existing messages into ChromaDB vector store")
    parser.add_argument("--summarise", action="store_true",
                        help="Generate weekly memory summary (needs Ollama)")
    parser.add_argument("--beliefs",   action="store_true",
                        help="Build / update belief index (needs Ollama)")
    parser.add_argument("--search",    metavar="QUERY",
                        help="Semantic search over your memories")
    parser.add_argument("--force",     action="store_true",
                        help="Force regenerate summary even if one exists")
    # ─────────────────────────────────────────────────────────────────────────
    args = parser.parse_args()

    print(BANNER)

    # Initialise database
    init_db()

    if args.stats:
        print_stats()
        # Also show Phase 2 vector store stats if available
        try:
            from backend.memory.store import get_store_stats
            print("\n🗂️  Vector store:")
            vstats = get_store_stats()
            for k, v in vstats.items():
                print(f"   {k}: {v}")
        except ImportError:
            pass
        return

    if args.import_file:
        import_file(args.import_file)
        return

    # ── Phase 2 CLI handlers ──────────────────────────────────────────────────
    if args.sync:
        try:
            from backend.memory.store import sync_from_sqlite
            from backend.ingest.storage import get_recent_messages
            print("[Agent] Syncing all messages to vector store...")
            messages = get_recent_messages(limit=10000)
            result = sync_from_sqlite(messages)
            print(f"[Agent] Sync complete: {result}")
        except ImportError:
            print("[Agent] Phase 2 not installed. Run: pip install chromadb sentence-transformers")
        return

    if args.summarise:
        try:
            from backend.memory.summariser import run_weekly_summary
            result = run_weekly_summary(force=args.force)
            if not result.get("skipped"):
                print(f"\nSummary:\n{result['summary_text']}")
                print(f"Topics: {', '.join(result.get('topics', []))}")
        except ImportError:
            print("[Agent] Phase 2 not installed. Run: pip install chromadb sentence-transformers ollama")
        return

    if args.beliefs:
        try:
            from backend.memory.belief_index import build_belief_index, get_top_beliefs
            result = build_belief_index()
            print(f"\nBelief index: {result}")
            print("\nTop beliefs:")
            for b in get_top_beliefs(limit=10):
                print(f"  [{b['topic']}] {b['belief_text']}")
        except ImportError:
            print("[Agent] Phase 2 not installed. Run: pip install chromadb sentence-transformers ollama")
        return

    if args.search:
        init_db()
        run_search(args.search)
        return
    # ─────────────────────────────────────────────────────────────────────────

    if args.voice:
        voice_mode()
    else:
        text_mode()


if __name__ == "__main__":
    main()