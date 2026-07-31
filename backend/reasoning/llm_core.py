"""
llm_core.py — Local LLM reasoning core
Phase 3: Retrieval & Reasoning Layer

This is the brain of the agent. It:
  1. Takes a user question
  2. Injects retrieved memories as context
  3. Calls the local Ollama LLM
  4. Returns an answer based ONLY on your memories

The LLM is strictly instructed:
  - Use only what's in the provided memories
  - Never invent information
  - If memories don't cover the topic → say so honestly
  - Match the language of the question (English / Hindi / Hinglish)
"""

import ollama
from backend.retrieval.retriever import retrieve_for_prompt
from backend.retrieval.ranker import rank_and_trim
from backend.retrieval.retriever import retrieve
from backend.memory.belief_index import get_belief_summary


# ---------------------------------------------------------------------------
# System prompt — the core instruction that makes this YOUR agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a digital version of the person who has been talking to you.
You think, speak, and reason exactly like them — because everything you know comes from their own words.

STRICT RULES:
1. Answer ONLY using the memories provided below. Never use outside knowledge.
2. If the memories don't contain relevant information, say exactly:
   "I haven't recorded my thoughts on this yet."
3. Speak in FIRST PERSON — you ARE the person, not an assistant describing them.
   Say "I think..." not "The person thinks..."
4. Match the language of the question:
   - English question → answer in English
   - Hindi question → answer in Hindi  
   - Hinglish question → answer in Hinglish
5. Be natural and conversational — not robotic or formal.
6. If multiple memories seem contradictory, acknowledge the tension honestly.
7. Never say "based on your memories" or "according to your notes" —
   just speak as if these are your own thoughts right now.
"""

NO_MEMORY_RESPONSES = {
    "english":  "I haven't recorded my thoughts on this yet. Ask me again after I've talked about it.",
    "hindi":    "मैंने अभी तक इस बारे में अपने विचार दर्ज नहीं किए हैं। कुछ दिन बात करने के बाद पूछना।",
    "hinglish": "Yaar, maine abhi tak is baare mein kuch nahi socha — ya kam se kam record nahi kiya. Baad mein poochh.",
}


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_prompt(query: str, context: str, language: str, belief_summary: str = "") -> str:
    """
    Build the full user-turn prompt with context injected.
    """
    belief_section = ""
    if belief_summary and belief_summary.strip():
        belief_section = f"""
MY CORE BELIEFS (always keep these in mind):
{belief_summary}
"""

    return f"""MY MEMORIES (use only these to answer):
{context}
{belief_section}
MY QUESTION ({language}):
{query}

Answer as me, in {language}:"""


# ---------------------------------------------------------------------------
# Core answer function
# ---------------------------------------------------------------------------

def ask(
    query:        str,
    language:     str  = "english",
    model:        str  = "mistral",
    top_k:        int  = 10,
    verbose:      bool = False,
    speak_answer: bool = False,   # Phase 4: speak the answer aloud
) -> dict:
    """
    Full pipeline: retrieve → rank → prompt → answer.

    Args:
        query:    The user's question
        language: Detected language of the query
        model:    Ollama model to use
        top_k:    Max context items to include
        verbose:  Print debug info

    Returns:
        {
            "answer":         str  — the generated answer
            "context_items":  list — ContextItems used
            "context_count":  int  — how many memories were used
            "had_context":    bool — whether any memories were found
            "model":          str
        }
    """

    # ── Step 1: Retrieve from all sources ───────────────────────────────────
    raw_items = retrieve(query, language=language)

    # ── Step 2: Re-rank + trim to token budget ───────────────────────────────
    ranked_items = rank_and_trim(raw_items, query=query, max_tokens=1800)

    if verbose:
        print(f"\n[LLM] Retrieved {len(raw_items)} items, using top {len(ranked_items)}")
        for item in ranked_items:
            print(f"  [{item.source}] {item.final_score:.3f} — {item.text[:60]}")

    # ── Step 3: Check if we have any context ────────────────────────────────
    if not ranked_items:
        no_mem = NO_MEMORY_RESPONSES.get(language, NO_MEMORY_RESPONSES["english"])
        return {
            "answer":        no_mem,
            "context_items": [],
            "context_count": 0,
            "had_context":   False,
            "model":         model,
        }

    # ── Step 4: Format context string ───────────────────────────────────────
    context = "\n".join(item.to_prompt_line() for item in ranked_items)

    # ── Step 5: Get belief summary for extra grounding ──────────────────────
    try:
        beliefs = get_belief_summary()
    except Exception:
        beliefs = ""

    # ── Step 6: Build prompt ─────────────────────────────────────────────────
    user_prompt = build_prompt(query, context, language, beliefs)

    if verbose:
        print(f"\n[LLM] Prompt preview:\n{user_prompt[:400]}...\n")

    # ── Step 7: Call local Ollama LLM ────────────────────────────────────────
    try:
        response = ollama.chat(
            model   = model,
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            options = {
                "temperature": 0.4,   # Slightly creative but mostly factual
                "top_p":       0.9,
                "num_predict": 400,   # Max tokens in response
            }
        )
        answer = response["message"]["content"].strip()

    except Exception as e:
        print(f"[LLM] Ollama error: {e}")
        print("[LLM] Make sure Ollama is running: ollama serve")
        raise

    result = {
        "answer":        answer,
        "context_items": ranked_items,
        "context_count": len(ranked_items),
        "had_context":   True,
        "model":         model,
    }

    # ── Phase 4 hook: speak the answer if TTS enabled ────────────────────────
    if speak_answer:
        try:
            from backend.output.language_router import prepare_for_speech
            from backend.output.tts_engine import get_tts
            prepared = prepare_for_speech(answer, language)
            tts = get_tts()
            for chunk in prepared["chunks"]:
                tts.speak(chunk, language=prepared["voice_language"])
        except ImportError:
            pass
        except Exception as e:
            print(f"[LLM] TTS error (non-fatal): {e}")
    # ─────────────────────────────────────────────────────────────────────────

    return result


# ---------------------------------------------------------------------------
# Multi-turn conversation session
# ---------------------------------------------------------------------------

class ConversationSession:
    """
    Maintains conversation history across multiple questions in one sitting.
    Injects previous turns into the prompt so the agent remembers
    what was said earlier in THIS conversation.

    Usage:
        session = ConversationSession()
        result  = session.ask("What do I think about mornings?")
        result2 = session.ask("And what about evenings?")  # knows the context
    """

    MAX_HISTORY_TURNS = 4   # Keep last 4 exchanges in context

    def __init__(self, model: str = "mistral"):
        self.model   = model
        self.history = []    # list of {"role": ..., "content": ...}

    def ask(self, query: str, language: str = "english", verbose: bool = False, speak_answer: bool = False) -> dict:
        """
        Ask a question, maintaining conversation history.
        """
        # Retrieve and rank memories
        raw_items    = retrieve(query, language=language)
        ranked_items = rank_and_trim(raw_items, query=query, max_tokens=1400)

        if not ranked_items and not self.history:
            no_mem = NO_MEMORY_RESPONSES.get(language, NO_MEMORY_RESPONSES["english"])
            return {
                "answer": no_mem, "context_items": [],
                "context_count": 0, "had_context": False, "model": self.model,
            }

        context = "\n".join(item.to_prompt_line() for item in ranked_items)

        try:
            beliefs = get_belief_summary()
        except Exception:
            beliefs = ""

        user_prompt = build_prompt(query, context, language, beliefs)

        # Build full messages array with history
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += self.history[-(self.MAX_HISTORY_TURNS * 2):]  # Last N turns
        messages.append({"role": "user", "content": user_prompt})

        try:
            response = ollama.chat(
                model    = self.model,
                messages = messages,
                options  = {"temperature": 0.4, "top_p": 0.9, "num_predict": 400}
            )
            answer = response["message"]["content"].strip()
        except Exception as e:
            print(f"[LLM] Ollama error: {e}")
            raise

        # ── Phase 4 hook: speak if enabled ──────────────────────────────────
        if speak_answer:
            try:
                from backend.output.language_router import prepare_for_speech
                from backend.output.tts_engine import get_tts
                prepared = prepare_for_speech(answer, language)
                tts = get_tts()
                for chunk in prepared["chunks"]:
                    tts.speak(chunk, language=prepared["voice_language"])
            except ImportError:
                pass
            except Exception as e:
                print(f"[LLM] TTS error (non-fatal): {e}")
        # ─────────────────────────────────────────────────────────────────────

        # Save to history
        self.history.append({"role": "user",      "content": user_prompt})
        self.history.append({"role": "assistant",  "content": answer})

        return {
            "answer":        answer,
            "context_items": ranked_items,
            "context_count": len(ranked_items),
            "had_context":   bool(ranked_items),
            "model":         self.model,
        }

    def clear(self):
        self.history = []
        print("[Session] Conversation history cleared.")


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== LLM Core Test ===\n")
    print("Testing single question...\n")

    result = ask(
        query    = "What do I think about discipline and consistency?",
        language = "english",
        verbose  = True,
    )

    print(f"\nAnswer:\n{result['answer']}")
    print(f"\nUsed {result['context_count']} memories. Had context: {result['had_context']}")

    print("\n\nTesting multi-turn session...\n")
    session = ConversationSession()
    r1 = session.ask("What are my thoughts on morning routines?", "english")
    print(f"Turn 1: {r1['answer'][:150]}...")
    r2 = session.ask("And how does that connect to my productivity?", "english")
    print(f"Turn 2: {r2['answer'][:150]}...")