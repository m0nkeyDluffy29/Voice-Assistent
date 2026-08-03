#!/usr/bin/env python3
"""
flux.py — Personal AI Agent CLI (JARVIS-style)

Single-file CLI voice assistant. Full offline. Works over SSH.
Uses your existing backend modules from the voice-assistant project.

Features:
    - Wake word detection (say "Flux" to activate)
    - Continuous conversation with VAD (auto-stops on silence)
    - Voice + text mode
    - Female TTS voice via espeak-ng
    - Memory of past conversations (SQLite)
    - Ollama Mistral for responses
    - Multi-lingual (English/Hindi/Hinglish)

Usage:
    flux                    # Wake-word listening mode (say "Flux" to talk)
    flux --chat             # Skip wake word, jump into conversation
    flux --text             # Text-only mode (type instead of speak)
    flux --name Jarvis      # Override agent name
    flux --lang english     # Force language (english/hindi/hinglish)
"""

import os
import sys
import time
import queue
import argparse
import subprocess
import threading
import signal
from pathlib import Path

# Add current dir to path so we can import skills
sys.path.insert(0, str(Path(__file__).parent))

# ---------------------------------------------------------------------------
# ANSI Colors
# ---------------------------------------------------------------------------
class C:
    PURPLE  = "\033[95m"
    CYAN    = "\033[96m"
    BLUE    = "\033[94m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    GRAY    = "\033[90m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RESET   = "\033[0m"

BANNER = f"""{C.PURPLE}
    ╔═══════════════════════════════════════╗
    ║   {C.BOLD}FLUX{C.RESET}{C.PURPLE} · Personal AI Agent CLI       ║
    ║   {C.DIM}offline · voice · memory-driven{C.RESET}{C.PURPLE}     ║
    ╚═══════════════════════════════════════╝
{C.RESET}"""

# ---------------------------------------------------------------------------
# Lazy imports — load only when needed for fast startup
# ---------------------------------------------------------------------------
_whisper_model = None
_vad_engine    = None
CONFIG_PATH    = Path.home() / ".flux_config"

def get_whisper():
    """Load faster-whisper — 4x faster than openai-whisper, no numba dependency."""
    global _whisper_model
    if _whisper_model is None:
        print(f"{C.GRAY}[boot] loading whisper tiny...{C.RESET}")
        from faster_whisper import WhisperModel
        # int8 quantization = tiny + very fast on CPU
        _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        print(f"{C.GRAY}[boot] whisper ready{C.RESET}")
    return _whisper_model

def get_vad():
    global _vad_engine
    if _vad_engine is None:
        try:
            import webrtcvad
            _vad_engine = webrtcvad.Vad(2)  # Aggressiveness 0-3
        except ImportError:
            print(f"{C.YELLOW}[warn] webrtcvad not installed — using simple silence detection{C.RESET}")
            _vad_engine = "fallback"
    return _vad_engine

# ---------------------------------------------------------------------------
# TTS — female voice via espeak-ng
# ---------------------------------------------------------------------------
def speak(text: str, language: str = "english", blocking: bool = True):
    """Speak text with espeak-ng using female voice settings."""
    if not text or not text.strip():
        return

    voice_map = {"english": "en+f3", "hindi": "hi+f3", "hinglish": "en+f3"}
    voice = voice_map.get(language, "en+f3")

    cmd = [
        "espeak-ng",
        "-v", voice,
        "-p", "60",       # Pitch (higher = more female)
        "-s", "160",      # Words per minute
        "-a", "180",      # Amplitude/volume
        "-g", "3",        # Small gap between words
        text,
    ]

    try:
        if blocking:
            subprocess.run(cmd, capture_output=True, timeout=30)
        else:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print(f"{C.RED}[error] espeak-ng not found. Install: sudo apt install espeak-ng{C.RESET}")
    except subprocess.TimeoutExpired:
        pass

# ---------------------------------------------------------------------------
# Voice recording with silence detection
# ---------------------------------------------------------------------------
def record_until_silence(max_seconds: int = 15, silence_ms: int = 1200, language: str = "english") -> str:
    """
    Record from mic until silence is detected.
    Returns transcribed text.
    """
    import sounddevice as sd
    import numpy as np
    from collections import deque

    SAMPLE_RATE = 16000
    CHUNK_MS    = 30
    CHUNK_SIZE  = int(SAMPLE_RATE * CHUNK_MS / 1000)

    vad = get_vad()
    frames = []
    silent_chunks = 0
    silent_threshold = silence_ms // CHUNK_MS
    speech_started = False
    max_chunks = int(max_seconds * 1000 / CHUNK_MS)

    print(f"{C.RED}● listening...{C.RESET}", end="\r", flush=True)

    q = queue.Queue()
    def callback(indata, frames_count, time_info, status):
        q.put(indata.copy())

    try:
        with sd.InputStream(
            samplerate  = SAMPLE_RATE,
            channels    = 1,
            dtype       = "int16",
            blocksize   = CHUNK_SIZE,
            callback    = callback,
        ):
            for _ in range(max_chunks):
                chunk = q.get()
                pcm   = chunk.tobytes()
                frames.append(chunk)

                # Check if this chunk is speech or silence
                if vad == "fallback":
                    # Simple amplitude-based fallback
                    amp = np.abs(chunk).mean()
                    is_speech = amp > 200
                else:
                    try:
                        is_speech = vad.is_speech(pcm, SAMPLE_RATE)
                    except Exception:
                        is_speech = np.abs(chunk).mean() > 200

                if is_speech:
                    speech_started = True
                    silent_chunks = 0
                elif speech_started:
                    silent_chunks += 1
                    if silent_chunks >= silent_threshold:
                        break

    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}[cancelled]{C.RESET}")
        return ""

    print(" " * 40, end="\r")   # Clear "listening..." line

    if not frames or not speech_started:
        return ""

    # Concatenate and transcribe
    import numpy as np
    audio_array = np.concatenate(frames).flatten().astype(np.float32) / 32768.0

    print(f"{C.BLUE}◐ transcribing...{C.RESET}", end="\r", flush=True)
    model = get_whisper()
    lang_code = {"english": "en", "hindi": "hi", "hinglish": None}.get(language)

    try:
        # faster-whisper returns segments, we join them
        segments, info = model.transcribe(
            audio_array,
            language     = lang_code,
            beam_size    = 1,          # Fastest — greedy decode
            vad_filter   = False,      # We already did VAD
            temperature  = 0.0,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        print(" " * 40, end="\r")
        return text
    except Exception as e:
        print(f"\n{C.RED}[transcribe error] {e}{C.RESET}")
        return ""

# ---------------------------------------------------------------------------
# Wake word — continuous listening for agent name
# ---------------------------------------------------------------------------
def wait_for_wake_word(agent_name: str, language: str = "english") -> bool:
    """Loop: listen 4s at a time, check if agent name was said."""
    name_lower = agent_name.lower()
    variants   = [name_lower, name_lower.replace(" ", "")]

    print(f"{C.GREEN}○ waiting for wake word: say '{C.BOLD}{agent_name}{C.RESET}{C.GREEN}'{C.RESET}")

    while True:
        try:
            text = record_until_silence(max_seconds=4, silence_ms=800, language=language)
            if not text:
                continue

            text_lower = text.lower()
            if any(v in text_lower for v in variants):
                print(f"{C.CYAN}✓ wake word detected: {C.DIM}'{text}'{C.RESET}")
                return True
        except KeyboardInterrupt:
            return False

# ---------------------------------------------------------------------------
# LLM — call Ollama Mistral with speed settings
# ---------------------------------------------------------------------------
def ask_llm(query: str, history: list, language: str = "english") -> str:
    """Get a fast conversational reply from Mistral."""
    import ollama

    system_prompt = (
        "You are a friendly AI assistant having a natural voice conversation. "
        "Rules: keep answers VERY SHORT (1 sentence, max 20 words), "
        "sound conversational and warm, never say 'as an AI', "
        f"reply in {language}."
    )

    # Try to load past memories if the query is longer than a short question
    context = ""
    if len(query) > 15:
        try:
            sys.path.insert(0, str(Path.cwd()))
            from backend.memory.store import search_memories
            memories = search_memories(query, top_k=2)
            if memories:
                context = "\n".join(f"- {m['text']}" for m in memories)
        except Exception:
            pass

    user_prompt = f"Context from past thoughts:\n{context}\n\nQuestion: {query}" if context else query

    messages = [{"role": "system", "content": system_prompt}]
    # Include last 4 turns for continuity
    messages.extend(history[-4:])
    messages.append({"role": "user", "content": user_prompt})

    try:
        response = ollama.chat(
            model    = "mistral",
            messages = messages,
            options  = {
                "temperature":    0.6,
                "top_p":          0.85,
                "num_predict":    50,
                "num_ctx":        512,
                "repeat_penalty": 1.15,
                "num_thread":     4,
            },
        )
        return response["message"]["content"].strip()
    except Exception as e:
        return f"Sorry, I could not reach Ollama. ({e})"

# ---------------------------------------------------------------------------
# Save turn to memory (async so it doesn't slow down the conversation)
# ---------------------------------------------------------------------------
def save_to_memory(user_text: str, agent_text: str, language: str = "english"):
    """Save both turns to SQLite + ChromaDB without blocking."""
    def _save():
        try:
            sys.path.insert(0, str(Path.cwd()))
            from backend.ingest.preprocessor import preprocess
            from backend.ingest.storage import save_message
            msg = preprocess(user_text, source="voice", force_language=language)
            save_message(msg)
        except Exception as e:
            pass  # Silent — memory save is optional
    threading.Thread(target=_save, daemon=True).start()

# ---------------------------------------------------------------------------
# Conversation loop
# ---------------------------------------------------------------------------
STOP_PHRASES = {"stop conversation", "stop", "exit", "quit", "goodbye", "bye", "band karo"}

def conversation_loop(agent_name: str, language: str = "english"):
    """Continuous conversation until user says stop."""
    history = []

    # Greeting
    greeting = f"Hi, I'm {agent_name}. How can I help you today?"
    print(f"{C.PURPLE}{agent_name}:{C.RESET} {greeting}")
    speak(greeting, language=language)

    while True:
        # Listen for user
        user_text = record_until_silence(max_seconds=15, silence_ms=1200, language=language)

        if not user_text:
            print(f"{C.DIM}(no speech — try again){C.RESET}")
            continue

        print(f"{C.CYAN}you:{C.RESET} {user_text}")

        # Check for stop phrases
        if any(phrase in user_text.lower() for phrase in STOP_PHRASES):
            farewell = "Goodbye. Talk soon."
            print(f"{C.PURPLE}{agent_name}:{C.RESET} {farewell}")
            speak(farewell, language=language)
            break

        # Try skills first (much faster than LLM)
        skill_response = None
        try:
            from skills import try_handle
            handled, skill_response = try_handle(user_text, agent_name, language)
        except ImportError:
            handled = False

        if handled and skill_response:
            print(f"{C.PURPLE}{agent_name}:{C.RESET} {skill_response} {C.DIM}(skill){C.RESET}")
            speak(skill_response, language=language)
            answer = skill_response
        else:
            # Fall back to LLM
            print(f"{C.BLUE}◐ thinking...{C.RESET}", end="\r", flush=True)
            t0 = time.time()
            answer = ask_llm(user_text, history, language)
            elapsed = time.time() - t0
            print(" " * 40, end="\r")
            print(f"{C.PURPLE}{agent_name}:{C.RESET} {answer} {C.DIM}({elapsed:.1f}s){C.RESET}")
            speak(answer, language=language)

        # Update history
        history.append({"role": "user",      "content": user_text})
        history.append({"role": "assistant", "content": answer})

        # Save to memory in background
        save_to_memory(user_text, answer, language)

        # Trim history to last 16 turns
        history = history[-16:]

# ---------------------------------------------------------------------------
# Text mode — for when you don't want voice
# ---------------------------------------------------------------------------
def text_mode(agent_name: str, language: str = "english"):
    """Type instead of speak — useful over SSH or noisy environments."""
    history = []
    greeting = f"Hi, I'm {agent_name}. Type your questions below (type 'exit' to quit)."
    print(f"{C.PURPLE}{agent_name}:{C.RESET} {greeting}\n")

    while True:
        try:
            user_text = input(f"{C.CYAN}you: {C.RESET}").strip()
            if not user_text:
                continue
            if user_text.lower() in STOP_PHRASES:
                print(f"{C.PURPLE}{agent_name}:{C.RESET} Goodbye.")
                break

            # Try skills first
            try:
                from skills import try_handle
                handled, skill_response = try_handle(user_text, agent_name, language)
            except ImportError:
                handled, skill_response = False, None

            if handled and skill_response:
                answer = skill_response
                print(f"{C.PURPLE}{agent_name}:{C.RESET} {answer} {C.DIM}(skill){C.RESET}\n")
            else:
                t0 = time.time()
                answer = ask_llm(user_text, history, language)
                elapsed = time.time() - t0
                print(f"{C.PURPLE}{agent_name}:{C.RESET} {answer} {C.DIM}({elapsed:.1f}s){C.RESET}\n")

            history.append({"role": "user",      "content": user_text})
            history.append({"role": "assistant", "content": answer})
            save_to_memory(user_text, answer, language)
            history = history[-16:]

        except (KeyboardInterrupt, EOFError):
            print(f"\n{C.PURPLE}{agent_name}:{C.RESET} Goodbye.")
            break

# ---------------------------------------------------------------------------
# Config — remember agent name across sessions
# ---------------------------------------------------------------------------
def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            import json
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}

def save_config(cfg: dict):
    try:
        import json
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass

def setup_agent_name(current: str = None) -> str:
    """Ask user to name their agent (first launch only)."""
    if current:
        return current
    print(f"{C.BOLD}First launch — let's name your agent.{C.RESET}")
    print(f"{C.DIM}Examples: Flux, Nova, Jarvis, Echo, Sage{C.RESET}")
    name = input(f"{C.YELLOW}Agent name: {C.RESET}").strip() or "Flux"
    save_config({"agent_name": name})
    print(f"{C.GREEN}✓ Saved. You can change this any time with --name{C.RESET}\n")
    return name

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description = "Flux — Personal AI Agent CLI",
        formatter_class = argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--chat",  action="store_true", help="Skip wake word, start conversation immediately")
    parser.add_argument("--text",  action="store_true", help="Text mode (type instead of speak)")
    parser.add_argument("--name",  metavar="NAME", help="Override agent name")
    parser.add_argument("--lang",  metavar="LANG", default="english",
                       choices=["english", "hindi", "hinglish"],
                       help="Language: english / hindi / hinglish")
    args = parser.parse_args()

    print(BANNER)

    # Load or set agent name
    cfg = load_config()
    agent_name = args.name or cfg.get("agent_name") or setup_agent_name()

    # Handle Ctrl+C gracefully
    def sigint_handler(sig, frame):
        print(f"\n{C.YELLOW}[interrupted] Goodbye.{C.RESET}")
        sys.exit(0)
    signal.signal(signal.SIGINT, sigint_handler)

    # Text mode
    if args.text:
        text_mode(agent_name, args.lang)
        return

    # Direct chat mode
    if args.chat:
        conversation_loop(agent_name, args.lang)
        return

    # Default: wake word mode
    print(f"{C.DIM}Tip: use --chat to skip wake word, --text for typing mode{C.RESET}\n")
    while True:
        if wait_for_wake_word(agent_name, args.lang):
            conversation_loop(agent_name, args.lang)
            print(f"\n{C.GRAY}[back to wake word mode]{C.RESET}\n")
        else:
            break

if __name__ == "__main__":
    main()