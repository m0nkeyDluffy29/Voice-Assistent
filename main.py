"""
main.py — Daily conversation interface
Personal AI Agent — Phase 1 + Phase 2 + Phase 3 + Phase 4

Two modes:
  FEED mode  — talk to it daily, build your memory bank
  ASK mode   — ask it questions, get SPOKEN answers from YOUR memories

Usage:
    python main.py                  # Feed mode: save your thoughts
    python main.py --ask            # Ask mode: answers spoken aloud (Phase 4)
    python main.py --ask --no-voice # Ask mode: text only (no speech)
    python main.py --voice          # Feed mode with voice input
    python main.py --tts-test       # Test TTS engine
    python main.py --stats          # Show all stats
    python main.py --import FILE    # Import notes from a text file
    python main.py --sync           # Backfill existing messages into ChromaDB
    python main.py --summarise      # Generate this week's memory summary
    python main.py --beliefs        # Build / update your belief index
    python main.py --search "query" # Semantic search over memories
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from backend.ingest.storage import init_db, save_message, get_stats, get_recent_messages
from backend.ingest.preprocessor import preprocess
from backend.ingest.listener import record_and_transcribe
from backend.ingest.language_utils import detect_language

# ---------------------------------------------------------------------------
# Banners and help text
# ---------------------------------------------------------------------------

BANNER = """
╔══════════════════════════════════════════════════════╗
║           🧠  Your Personal AI Agent                 ║
║           Talk to it daily. It remembers.            ║
╚══════════════════════════════════════════════════════╝
"""

FEED_HELP = """
── FEED MODE — saving your thoughts ──────────────────────────
  /ask            — switch to ASK mode (ask questions)
  /quit or /exit  — end the session
  /stats          — show memory + vector store stats
  /recent         — show your last 5 messages
  /voice          — record one voice message
  /search <query> — search your memories semantically
  /beliefs        — show your belief index
  /summarise      — generate this week's summary
  /help           — show this help

Just type normally to save a thought, opinion, or experience.
English, Hindi, or Hinglish — all three work.
"""

ASK_HELP = """
── ASK MODE — talking to your digital self ───────────────────
  /feed           — switch back to FEED mode (save thoughts)
  /quit or /exit  — end the session
  /clear          — clear conversation history (fresh start)
  /voice          — speak your question instead of typing
  /mute           — toggle voice output on/off
  /engine         — show which TTS engine is active
  /help           — show this help

Ask anything. The agent speaks its answer from your own memories.
If it hasn't been told about something, it will say so honestly.
"""

# ---------------------------------------------------------------------------
# FEED mode — save thoughts
# ---------------------------------------------------------------------------

def text_mode():
    """FEED mode — save daily thoughts and opinions."""
    print(FEED_HELP)
    session_count = 0

    while True:
        try:
            raw = input("\n[FEED] You → ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n[Agent] Session ended. Goodbye!")
            break

        if not raw:
            continue

        if raw.lower() in ("/quit", "/exit", "quit", "exit", "bye"):
            print("\n[Agent] Session ended. See you tomorrow!")
            break

        if raw.lower() == "/help":
            print(FEED_HELP)
            continue

        if raw.lower() == "/ask":
            print("\n[Agent] Switching to ASK mode...")
            ask_mode()
            print("\n[Agent] Back to FEED mode.")
            continue

        if raw.lower() == "/stats":
            print_stats()
            continue

        if raw.lower() == "/recent":
            print_recent()
            continue

        if raw.lower().startswith("/search "):
            query = raw[8:].strip()
            run_search(query) if query else print("[Agent] Usage: /search <query>")
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

        # Save the message
        try:
            msg   = preprocess(raw, source="text")
            saved = save_message(msg)
            if saved:
                lang_label  = {"english": "EN", "hindi": "HI", "hinglish": "HI+EN"}.get(msg["language"], "?")
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
# ASK mode — Phase 3: question-answer using your memories
# ---------------------------------------------------------------------------

def ask_mode(voice_output: bool = True):
    """ASK mode — answers retrieved from your memories and spoken aloud."""
    try:
        from backend.reasoning.llm_core import ConversationSession
        from backend.ingest.language_utils import detect_language
    except ImportError:
        print("[Agent] Phase 3 not installed. Run: pip install ollama chromadb sentence-transformers")
        return

    # Check if Phase 4 TTS is available
    tts_available = False
    try:
        from backend.output.tts_engine import get_tts
        tts = get_tts()
        tts_available = True
        speak_answers = voice_output
        if speak_answers:
            print(f"[Agent] Voice output: ON (engine={tts.get_engine_name()})")
        else:
            print("[Agent] Voice output: OFF (--no-voice mode)")
    except ImportError:
        speak_answers = False
        print("[Agent] Voice output unavailable. Install: pip install piper-tts pyttsx3")

    print(ASK_HELP)
    session = ConversationSession()
    print("[Agent] Ready. Ask me anything about yourself.\n")

    while True:
        try:
            raw = input("\n[ASK] You → ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Agent] Leaving ASK mode.")
            break

        if not raw:
            continue

        if raw.lower() in ("/quit", "/exit", "quit", "exit"):
            break

        if raw.lower() == "/feed":
            print("[Agent] Switching back to FEED mode.")
            break

        if raw.lower() == "/help":
            print(ASK_HELP)
            continue

        if raw.lower() == "/clear":
            session.clear()
            print("[Agent] Conversation history cleared.")
            continue

        if raw.lower() == "/mute":
            speak_answers = not speak_answers
            state = "ON" if speak_answers else "OFF"
            print(f"[Agent] Voice output: {state}")
            continue

        if raw.lower() == "/engine":
            if tts_available:
                from backend.output.tts_engine import get_tts
                print(f"[Agent] TTS engine: {get_tts().get_engine_name()}")
            else:
                print("[Agent] TTS not available.")
            continue

        if raw.lower() == "/voice":
            result = record_and_transcribe()
            raw = result["text"]
            if not raw:
                print("[Agent] Couldn't catch that. Try again.")
                continue
            print(f"[Agent] Heard: {raw}")

        language = detect_language(raw)
        print("[Agent] Thinking...", end="\r")

        try:
            result = session.ask(raw, language=language, speak_answer=speak_answers)
            print(" " * 30, end="\r")
            print(f"\n[Agent] {result['answer']}")
            if result["context_count"] > 0:
                print(f"\n        (based on {result['context_count']} memories)")
            else:
                print()
        except Exception as e:
            print(f"\n[Agent] Error: {e}")
            print("[Agent] Make sure Ollama is running: ollama serve")


# ---------------------------------------------------------------------------
# Voice feed mode
# ---------------------------------------------------------------------------

def voice_mode():
    """Full voice FEED loop."""
    print("\n[Agent] Voice FEED mode. Press Enter to record, /quit to exit.\n")

    while True:
        cmd = input("Press Enter to speak (or /quit): ").strip().lower()

        if cmd in ("/quit", "quit", "exit"):
            print("[Agent] Session ended.")
            break

        result = record_and_transcribe()
        raw    = result["text"]

        if not raw:
            print("[Agent] Nothing captured. Try again.")
            continue

        print(f"[Agent] Heard ({result['language']}): {raw}")
        msg   = preprocess(raw, source="voice", force_language=result["language"])
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
# Helper functions
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
    try:
        from backend.memory.store import get_store_stats
        vstats = get_store_stats()
        print("\n🗂️  Vector store:")
        for k, v in vstats.items():
            print(f"   {k}: {v}")
    except ImportError:
        pass


def print_recent():
    messages = get_recent_messages(limit=5)
    if not messages:
        print("\n[Agent] No messages yet. Start talking!")
        return
    print("\n📖 Your last 5 entries:")
    for m in messages:
        ts   = m["timestamp"][:10]
        lang = m["language"][:2].upper()
        print(f"   [{ts}][{lang}] {m['text'][:80]}")


def run_search(query: str):
    """Phase 2: raw semantic search."""
    try:
        from backend.memory.store import search_memories
        print(f"\n🔍 Searching: '{query}'")
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
        from backend.memory.belief_index import get_top_beliefs, get_belief_count
        count = get_belief_count()
        if count == 0:
            print("\n[Agent] No beliefs indexed yet. Run: python main.py --beliefs")
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
        print("\n📝 Generating weekly summary...")
        result = run_weekly_summary()
        if result.get("skipped"):
            reason = result.get("reason", "unknown")
            msg = "Summary already exists. Use --force to regenerate." if reason == "already_exists" else f"Skipped: {reason}"
            print(f"[Agent] {msg}")
        else:
            print(f"\n--- Summary ---\n{result['summary_text']}")
            if result.get("topics"):
                print(f"\nTopics: {', '.join(result['topics'])}")
    except ImportError:
        print("[Agent] Phase 2 not installed. Run: pip install chromadb sentence-transformers ollama")


# ---------------------------------------------------------------------------
# Phase 4 helpers
# ---------------------------------------------------------------------------

def run_tts_test():
    print("TTS Engine Test")
    """Test the TTS engine with sample text in all three languages."""

    try:
        from backend.output.tts_engine import TTSEngine
        from backend.output.language_router import prepare_for_speech

        tts = TTSEngine()
        print(f"Engine: {tts.get_engine_name()}")

        samples = [
            ("I believe that discipline is the foundation of everything I do.", "english"),
            ("Yaar mujhe lagta hai ki consistency bahut zaroor hai zindagi mein.", "hinglish"),
            ("मुझे लगता है कि परिवार सबसे पहले आता है।", "hindi"),
        ]

        for text, lang in samples:
            print(f"[{lang.upper()}] {text}")
            prepared = prepare_for_speech(text, lang)
            for chunk in prepared["chunks"]:
                tts.speak(chunk, language=prepared["voice_language"])
            print()

        print("TTS test complete.")
    except ImportError:
        print("[Agent] Phase 4 not installed.")
        print("        Install: pip install piper-tts sounddevice soundfile")
        print("        Fallback: pip install pyttsx3")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Personal AI Agent")
    parser.add_argument("--voice",     action="store_true", help="Voice FEED mode")
    parser.add_argument("--ask",       action="store_true", help="Start in ASK mode (Phase 3)")
    parser.add_argument("--stats",     action="store_true", help="Show stats and exit")
    parser.add_argument("--import",    dest="import_file", metavar="FILE")
    # Phase 2
    parser.add_argument("--sync",      action="store_true")
    parser.add_argument("--summarise", action="store_true")
    parser.add_argument("--beliefs",   action="store_true")
    parser.add_argument("--search",    metavar="QUERY")
    parser.add_argument("--force",     action="store_true")
    # Phase 4
    parser.add_argument("--no-voice",  dest="no_voice",  action="store_true", help="Disable voice output in ASK mode")
    parser.add_argument("--ttstest",   dest="tts_test",  action="store_true", help="Test TTS engine and exit")
    args = parser.parse_args()

    print(BANNER)
    init_db()

    if args.stats:
        print_stats()
        return

    if args.import_file:
        import_file(args.import_file)
        return

    if args.sync:
        try:
            from backend.memory.store import sync_from_sqlite
            messages = get_recent_messages(limit=10000)
            result   = sync_from_sqlite(messages)
            print(f"[Agent] Sync complete: {result}")
        except ImportError:
            print("[Agent] Phase 2 not installed.")
        return

    if args.summarise:
        try:
            from backend.memory.summariser import run_weekly_summary
            result = run_weekly_summary(force=args.force)
            if not result.get("skipped"):
                print(f"\nSummary:\n{result['summary_text']}")
        except ImportError:
            print("[Agent] Phase 2 not installed.")
        return

    if args.beliefs:
        try:
            from backend.memory.belief_index import build_belief_index, get_top_beliefs
            result = build_belief_index()
            print(f"\nBelief index: {result}")
            for b in get_top_beliefs(limit=10):
                print(f"  [{b['topic']}] {b['belief_text']}")
        except ImportError:
            print("[Agent] Phase 2 not installed.")
        return

    if args.search:
        run_search(args.search)
        return

    # ── Phase 4: TTS test ────────────────────────────────────────────────────
    if args.tts_test:
        run_tts_test()
        return

    # ── Phase 3+4: ASK mode ──────────────────────────────────────────────────
    if args.ask:
        voice_output = not args.no_voice
        ask_mode(voice_output=voice_output)
        return

    if args.voice:
        voice_mode()
    else:
        text_mode()


if __name__ == "__main__":
    main()