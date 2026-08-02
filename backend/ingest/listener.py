"""
listener.py — Voice input using OpenAI Whisper (fully offline)
Phase 1: Data Ingestion Layer

Handles:
- Recording audio from microphone (push-to-talk)
- Transcribing audio files to text
- Auto-detecting language (English / Hindi / Hinglish)
"""

import os
import wave
import tempfile
import threading
import whisper
import sounddevice as sd
import numpy as np

# ---------------------------------------------------------------------------
# Model loader (downloads once, cached locally in models/whisper/)
# ---------------------------------------------------------------------------

MODEL_DIR = os.path.join(os.path.dirname(__file__), "../../models/whisper")
_model = None


def get_model(size: str = "base") -> whisper.Whisper:
    """
    Load Whisper model once and reuse.
    'base' is default — 5x faster than medium, good for conversation.
    Sizes: tiny | base | small | medium | large
    """
    global _model
    if _model is None:
        os.makedirs(MODEL_DIR, exist_ok=True)
        print(f"[Listener] Loading Whisper '{size}' model (first load may take a moment)...")
        _model = whisper.load_model(size, download_root=MODEL_DIR)
        print("[Listener] Whisper model ready.")
    return _model


# ---------------------------------------------------------------------------
# Transcribe an audio file
# ---------------------------------------------------------------------------

def transcribe_file(audio_path: str, language: str = None) -> dict:
    """
    Transcribe an audio file to text.

    Args:
        audio_path: Path to a .wav or .mp3 file
        language:   Force a language code ('en', 'hi') or None for auto-detect

    Returns:
        {
            "text":     str  — transcribed text
            "language": str  — detected language code ('en', 'hi', etc.)
            "segments": list — word-level segments (timestamps)
        }
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    model = get_model()
    print(f"[Listener] Transcribing: {audio_path}")

    result = model.transcribe(
        audio_path,
        language=language,          # None = auto-detect
        task="transcribe",          # 'translate' would translate to English
        fp16=False,                 # safer for CPU-only machines
        verbose=False
    )

    return {
        "text": result["text"].strip(),
        "language": result.get("language", "en"),
        "segments": result.get("segments", [])
    }


# ---------------------------------------------------------------------------
# Record from microphone
# ---------------------------------------------------------------------------

class MicRecorder:
    """
    Push-to-talk microphone recorder.
    Call start() to begin, stop() to end and get the audio path.

    Usage:
        recorder = MicRecorder()
        recorder.start()
        input("Press Enter to stop...")
        audio_path = recorder.stop()
        result = transcribe_file(audio_path)
    """

    SAMPLE_RATE = 16000     # Whisper expects 16kHz
    CHANNELS = 1            # Mono
    DTYPE = np.float32

    def __init__(self):
        self._frames = []
        self._recording = False
        self._thread = None
        self._tmp_path = None

    def start(self):
        """Start recording from the default microphone."""
        self._frames = []
        self._recording = True
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()
        print("[Mic] Recording started — speak now...")

    def _record_loop(self):
        with sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            dtype=self.DTYPE,
            blocksize=1024
        ) as stream:
            while self._recording:
                chunk, _ = stream.read(1024)
                self._frames.append(chunk.copy())

    def stop(self) -> str:
        """
        Stop recording and save to a temp .wav file.

        Returns:
            Path to the saved .wav file
        """
        self._recording = False
        if self._thread:
            self._thread.join(timeout=2)

        audio_data = np.concatenate(self._frames, axis=0)

        # Save to a named temp file (caller is responsible for cleanup)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self._tmp_path = tmp.name
        tmp.close()

        with wave.open(self._tmp_path, "wb") as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(2)                  # 16-bit PCM
            wf.setframerate(self.SAMPLE_RATE)
            pcm = (audio_data * 32767).astype(np.int16)
            wf.writeframes(pcm.tobytes())

        duration = len(audio_data) / self.SAMPLE_RATE
        print(f"[Mic] Recording stopped — {duration:.1f}s saved to {self._tmp_path}")
        return self._tmp_path


# ---------------------------------------------------------------------------
# Convenience: record + transcribe in one call
# ---------------------------------------------------------------------------

def record_and_transcribe() -> dict:
    """
    Interactive: press Enter to start, Enter again to stop.
    Returns the transcription dict.
    """
    recorder = MicRecorder()
    input("[Listener] Press Enter to START recording...")
    recorder.start()
    input("[Listener] Press Enter to STOP recording...")
    audio_path = recorder.stop()

    result = transcribe_file(audio_path)

    # Clean up temp file
    try:
        os.unlink(audio_path)
    except OSError:
        pass

    print(f"[Listener] Transcribed ({result['language']}): {result['text']}")
    return result


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Listener test ===")
    result = record_and_transcribe()
    print("\nResult:")
    print(f"  Text:     {result['text']}")
    print(f"  Language: {result['language']}")