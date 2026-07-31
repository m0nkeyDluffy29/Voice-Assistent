"""
tts_engine.py — Offline Text-to-Speech engine
Phase 4: Voice Output Layer

Converts the agent's text answers into spoken audio — fully offline.
No internet needed after first model download.

Supports:
    English  → Piper TTS (fast, lightweight, CPU-friendly, Python 3.12+)
    Hindi    → Piper TTS with Hindi voice
    Hinglish → English voice (Latin script output)

Fallback chain:
    Piper TTS → pyttsx3 (system TTS) → print only

Install:
    pip install piper-tts sounddevice soundfile   (primary)
    pip install pyttsx3                           (fallback)
"""

import os
import sys
import tempfile
import threading
import time
import urllib.request
from typing import Optional

BASE_DIR  = os.path.join(os.path.dirname(__file__), "../../")
MODEL_DIR = os.path.join(BASE_DIR, "models/tts")

# ---------------------------------------------------------------------------
# Audio playback
# ---------------------------------------------------------------------------

def _play_wav(wav_path: str):
    """Play a WAV file using sounddevice."""
    try:
        import soundfile as sf
        import sounddevice as sd
        data, samplerate = sf.read(wav_path)
        sd.play(data, samplerate)
        sd.wait()
    except Exception as e:
        print(f"[TTS] Playback error: {e}")

# ---------------------------------------------------------------------------
# Piper TTS voice registry
# ---------------------------------------------------------------------------

PIPER_VOICES = {
    "english": {
        "name":   "en_US-lessac-medium",
        "url":    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "config": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
    },
    "hindi": {
        "name":   "hi_IN-pratham-medium",
        "url":    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/hi/hi_IN/pratham/medium/hi_IN-pratham-medium.onnx",
        "config": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/hi/hi_IN/pratham/medium/hi_IN-pratham-medium.onnx.json",
    },
    "hinglish": {
        # Hinglish uses English voice — output is always Latin script
        "name":   "en_US-lessac-medium",
        "url":    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "config": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
    },
}

def _download_piper_voice(language: str) -> tuple:
    """Download voice model if not cached. Returns (model_path, config_path)."""
    voice = PIPER_VOICES.get(language, PIPER_VOICES["english"])
    os.makedirs(MODEL_DIR, exist_ok=True)

    model_path  = os.path.join(MODEL_DIR, f"{voice['name']}.onnx")
    config_path = os.path.join(MODEL_DIR, f"{voice['name']}.onnx.json")

    if not os.path.exists(model_path):
        print(f"[TTS] Downloading {language} voice (~60 MB, one-time)...")
        urllib.request.urlretrieve(voice["url"], model_path)
        print(f"[TTS] Voice saved: {model_path}")

    if not os.path.exists(config_path):
        urllib.request.urlretrieve(voice["config"], config_path)

    return model_path, config_path

# ---------------------------------------------------------------------------
# Engine 1: Piper TTS (primary)
# ---------------------------------------------------------------------------

class PiperEngine:
    """Piper TTS — fast, offline, Python 3.12 compatible."""

    def __init__(self):
        self._voices = {}

    def _get_voice(self, language: str):
        if language not in self._voices:
            from piper.voice import PiperVoice
            model_path, config_path = _download_piper_voice(language)
            self._voices[language] = PiperVoice.load(
                model_path, config_path=config_path, use_cuda=False
            )
        return self._voices[language]

    def synthesise(self, text: str, language: str, output_path: str) -> bool:
        try:
            import wave
            voice = self._get_voice(language)
            with wave.open(output_path, "wb") as wf:
                voice.synthesize(text, wf)
            return True
        except ImportError:
            return False
        except Exception as e:
            print(f"[TTS/Piper] Error: {e}")
            return False

    def is_available(self) -> bool:
        try:
            import piper
            return True
        except ImportError:
            return False

# ---------------------------------------------------------------------------
# Engine 2: pyttsx3 (fallback)
# ---------------------------------------------------------------------------

class Pyttsx3Engine:
    """pyttsx3 fallback — uses OS system TTS voices."""

    def __init__(self):
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", 155)
            self._engine.setProperty("volume", 0.95)
        return self._engine

    def speak_direct(self, text: str, language: str):
        """Speak directly (no WAV file needed)."""
        try:
            engine = self._get_engine()
            if language == "hindi":
                for v in engine.getProperty("voices"):
                    if "hindi" in v.name.lower() or "hi_IN" in v.id:
                        engine.setProperty("voice", v.id)
                        break
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            print(f"[TTS/pyttsx3] Error: {e}")

    def synthesise(self, text: str, language: str, output_path: str) -> bool:
        try:
            engine = self._get_engine()
            engine.save_to_file(text, output_path)
            engine.runAndWait()
            return os.path.exists(output_path)
        except Exception as e:
            print(f"[TTS/pyttsx3] Synthesis error: {e}")
            return False

    def is_available(self) -> bool:
        try:
            import pyttsx3
            return True
        except ImportError:
            return False

# ---------------------------------------------------------------------------
# Main TTS interface
# ---------------------------------------------------------------------------

class TTSEngine:
    """
    Unified TTS interface. Auto-selects best available engine.

    Priority: Piper → pyttsx3 → print

    Usage:
        tts = TTSEngine()
        tts.speak("I think consistency is key", language="english")
        tts.speak("Yaar bahut kaam hua aaj", language="hinglish")
    """

    def __init__(self, preferred_engine: str = "auto"):
        self._piper   = PiperEngine()
        self._pyttsx3 = Pyttsx3Engine()
        self._engine  = self._select_engine(preferred_engine)
        print(f"[TTS] Engine: {self._engine}")

    def _select_engine(self, preferred: str) -> str:
        if preferred != "auto":
            return preferred
        if self._piper.is_available():
            return "piper"
        if self._pyttsx3.is_available():
            return "pyttsx3"
        return "print"

    def speak(
        self,
        text:     str,
        language: str  = "english",
        blocking: bool = True,
        save_to:  str  = None,
    ) -> Optional[str]:
        """
        Speak text aloud.

        Args:
            text:     Text to synthesise
            language: 'english' | 'hindi' | 'hinglish'
            blocking: Wait until audio finishes if True
            save_to:  Save WAV to this path (optional)

        Returns:
            WAV file path if save_to provided, else None
        """
        if not text or not text.strip():
            return None

        tmp_path = None
        if self._engine == "piper" or (self._engine == "pyttsx3" and not blocking):
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = save_to or tmp.name
            tmp.close()

        success = False

        if self._engine == "piper":
            success = self._piper.synthesise(text, language, tmp_path)
            if success:
                if blocking:
                    _play_wav(tmp_path)
                else:
                    threading.Thread(target=_play_wav, args=(tmp_path,), daemon=True).start()

        elif self._engine == "pyttsx3":
            if blocking:
                self._pyttsx3.speak_direct(text, language)
                success = True
            else:
                success = self._pyttsx3.synthesise(text, language, tmp_path)
                if success:
                    threading.Thread(target=_play_wav, args=(tmp_path,), daemon=True).start()

        else:
            # Print fallback — always works
            lang_icon = {"english": "🔊", "hindi": "🔊", "hinglish": "🔊"}.get(language, "🔊")
            print(f"\n{lang_icon} {text}\n")
            success = True

        # Cleanup temp file if we're not saving
        if tmp_path and not save_to and blocking and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return save_to if save_to and success else None

    def speak_async(self, text: str, language: str = "english"):
        """Non-blocking: returns immediately, speaks in background thread."""
        return self.speak(text, language, blocking=False)

    def get_engine_name(self) -> str:
        return self._engine

    def set_engine(self, engine: str):
        """Switch engine at runtime: 'piper' | 'pyttsx3' | 'print'"""
        self._engine = engine
        print(f"[TTS] Switched to: {engine}")

# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_tts_instance: Optional[TTSEngine] = None

def get_tts() -> TTSEngine:
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = TTSEngine()
    return _tts_instance

def speak(text: str, language: str = "english", blocking: bool = True):
    """
    Module-level convenience. Import and call anywhere:
        from backend.output.tts_engine import speak
        speak("My answer here", language="english")
    """
    get_tts().speak(text, language, blocking=blocking)

# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== TTS Engine Test ===\n")
    tts = TTSEngine()
    print(f"Engine: {tts.get_engine_name()}\n")

    tests = [
        ("I believe discipline is the foundation of everything I do.", "english"),
        ("Yaar mujhe lagta hai ki consistency se hi sab kuch milta hai.", "hinglish"),
        ("मुझे लगता है कि परिवार सबसे पहले आता है।", "hindi"),
    ]

    for text, lang in tests:
        print(f"[{lang}] {text}")
        tts.speak(text, language=lang)
        time.sleep(0.3)

    print("\nAll tests done.")