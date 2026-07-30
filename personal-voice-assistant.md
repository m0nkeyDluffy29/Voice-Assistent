# 🧠 Personal AI Agent — Your Digital Self

> An offline, voice-enabled AI that learns exclusively from your daily conversations and answers questions the way *you* would — not from Google, not from the internet, only from what you have told it.

---

## 📌 What This Is

Most AI systems answer from the internet or their training data. This agent is different.

- It only knows what **you** have told it
- It speaks back to you — no reading required
- It works **fully offline** on your device
- It understands **English, Hindi, and Hinglish**
- Over time it becomes a digital mirror of your mind — your opinions, values, patterns, and experiences

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────┐
│              INPUT LAYER                            │
│   Your typed text · Voice recordings · Pasted notes │
└───────────────────┬─────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────┐
│              PREPROCESSING ENGINE                   │
│   Language detection · Hinglish normaliser          │
│   Entity tagging · Deduplication                    │
└───────────────────┬─────────────────────────────────┘
                    │
                    ▼
┌──────────────┬────────────────┬─────────────────────┐
│  RAW LOGS    │   SUMMARIES    │   BELIEF INDEX       │
│  Every msg,  │  Weekly digest │  Your opinions,      │
│  timestamped │  of your views │  values, patterns    │
│              │                │                      │
│      Local Vector Database (on-device, offline)      │
└──────────────┴────────────────┴──────────┬──────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────┐
│         RETRIEVAL + REASONING CORE                  │
│   Finds relevant memories · Ranks by recency        │
│   Generates answer strictly from your conversations │
└──────────────────┬──────────────────────────────────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
┌──────────────────┐  ┌──────────────────────┐
│  LANGUAGE LAYER  │  │   VOICE OUTPUT (TTS) │
│  English · Hindi │→ │   Offline TTS engine │
│  Hinglish detect │  │   No reading needed  │
└──────────────────┘  └──────────────────────┘
                   │
                   ▼
        🔊 Answer spoken in your voice style
           Based only on what you told it
```

---

## 🛠️ Recommended Tech Stack

| Component | Tool | Why |
|---|---|---|
| Local LLM | Ollama + Mistral 7B / Llama 3.1 8B | Runs fully offline, low RAM |
| Vector DB | ChromaDB or SQLite + embeddings | On-device, no cloud needed |
| Embeddings | `sentence-transformers` (offline) | Multilingual, fast |
| Voice Input (STT) | OpenAI Whisper (offline mode) | Handles Hindi, Hinglish, English |
| Voice Output (TTS) | Coqui TTS or Piper TTS | Offline, supports Hindi + English |
| Backend | **Python** | Best ecosystem for all above tools |
| Frontend / UI | **React + Tauri** (desktop app) | Cross-platform, lightweight |
| Language Detection | `langdetect` or `lingua-py` | Fast, no internet needed |

### Why Python as the primary language?

Python has the richest ecosystem for everything this project needs — Whisper, ChromaDB, sentence-transformers, Ollama API, Coqui TTS — all have first-class Python support. No other language comes close for this specific combination of ML + audio + vector search.

Tauri (Rust + React frontend) is used only for the desktop UI shell. All the heavy logic stays in Python.

---

## 📁 Project Structure

```
personal-ai-agent/
│
├── backend/                    # Python — all core logic
│   ├── ingest/
│   │   ├── listener.py         # Voice input via Whisper
│   │   ├── preprocessor.py     # Clean, tag, detect language
│   │   └── language_utils.py   # Hinglish normaliser
│   │
│   ├── memory/
│   │   ├── store.py            # ChromaDB vector store
│   │   ├── summariser.py       # Weekly summary generator
│   │   └── belief_index.py     # Opinion/pattern tracker
│   │
│   ├── retrieval/
│   │   ├── retriever.py        # Semantic search over memories
│   │   └── ranker.py           # Recency + relevance scoring
│   │
│   ├── reasoning/
│   │   └── llm_core.py         # Ollama local LLM interface
│   │
│   ├── output/
│   │   ├── tts_engine.py       # Coqui / Piper TTS
│   │   └── language_router.py  # Pick voice/lang based on query
│   │
│   └── api/
│       └── server.py           # FastAPI server for frontend
│
├── frontend/                   # React + Tauri desktop UI
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── ChatWindow.jsx
│   │   │   ├── VoiceButton.jsx
│   │   │   └── MemoryPanel.jsx
│   │   └── hooks/
│   │       └── useConversation.js
│   └── src-tauri/              # Tauri desktop shell (Rust)
│
├── data/                       # All stored locally, never uploaded
│   ├── raw_logs/
│   ├── summaries/
│   ├── chroma_db/
│   └── embeddings/
│
├── models/                     # Downloaded model files (offline)
│   ├── whisper/
│   ├── tts/
│   └── embeddings/
│
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🚀 Phase-wise Development Plan

---

### Phase 1 — Foundation & Data Ingestion

**Goal:** Accept your daily conversations, clean them, and store them locally.

**Language:** Python

**What to build:**
- A simple CLI or chat window to accept text input
- Whisper integration for voice input (offline)
- Language detector (English / Hindi / Hinglish)
- Hinglish text normaliser
- Store raw conversations in SQLite with timestamps

**Key files:** `listener.py`, `preprocessor.py`, `language_utils.py`

```python
# listener.py — voice input using Whisper (offline)
import whisper

model = whisper.load_model("medium")  # supports Hindi

def transcribe_audio(audio_path: str) -> dict:
    result = model.transcribe(audio_path, language=None)  # auto-detect
    return {
        "text": result["text"],
        "language": result["language"]
    }
```

```python
# preprocessor.py — clean and tag each message
from lingua import Language, LanguageDetectorBuilder
import re

detector = LanguageDetectorBuilder.from_languages(
    Language.ENGLISH, Language.HINDI
).build()

def preprocess(raw_text: str) -> dict:
    text = raw_text.strip()
    detected = detector.detect_language_of(text)
    lang = "hinglish" if is_hinglish(text, detected) else detected.iso_code_639_1.name.lower()
    return {
        "text": text,
        "language": lang,
        "entities": extract_entities(text),
        "timestamp": get_timestamp()
    }

def is_hinglish(text: str, detected) -> bool:
    # Hinglish = Latin script but Hindi vocabulary patterns
    hindi_markers = ["hai", "hain", "nahi", "tha", "ke", "ka", "ki", "mein", "se"]
    words = text.lower().split()
    score = sum(1 for w in words if w in hindi_markers)
    return score >= 2 and not any(ord(c) > 127 for c in text)
```

```python
# storage — SQLite raw log
import sqlite3, json
from datetime import datetime

def save_message(processed: dict):
    conn = sqlite3.connect("data/raw_logs/conversations.db")
    conn.execute("""
        INSERT INTO messages (text, language, entities, timestamp)
        VALUES (?, ?, ?, ?)
    """, (
        processed["text"],
        processed["language"],
        json.dumps(processed["entities"]),
        processed["timestamp"]
    ))
    conn.commit()
    conn.close()
```

**Packages to install:**
```bash
pip install openai-whisper lingua-language-detector sqlite3
```

**Milestone:** You can talk to the app and it saves everything you say, locally, with language tags.

---

### Phase 2 — Memory Layer (Vector Database)

**Goal:** Convert stored conversations into searchable vector embeddings so the AI can find relevant memories fast.

**Language:** Python

**What to build:**
- Load sentences into ChromaDB using multilingual embeddings
- Build a weekly summariser that digests your conversations into compact summaries
- Build a belief index that extracts recurring opinions and values from your messages

**Key files:** `store.py`, `summariser.py`, `belief_index.py`

```python
# store.py — embed and store in ChromaDB
import chromadb
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
client = chromadb.PersistentClient(path="data/chroma_db")
collection = client.get_or_create_collection("memories")

def add_memory(text: str, metadata: dict):
    embedding = model.encode(text).tolist()
    collection.add(
        documents=[text],
        embeddings=[embedding],
        metadatas=[metadata],
        ids=[metadata["id"]]
    )

def search_memories(query: str, top_k: int = 5) -> list:
    query_embedding = model.encode(query).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k
    )
    return results["documents"][0]
```

```python
# summariser.py — weekly digest using local LLM
import ollama

def summarise_week(conversations: list[str]) -> str:
    joined = "\n".join(conversations)
    response = ollama.chat(model="mistral", messages=[{
        "role": "user",
        "content": f"""
You are summarising a person's own private conversations.
Extract their main opinions, experiences, and decisions.
Be concise. Use only what is in the text below.

Conversations:
{joined}

Summary:"""
    }])
    return response["message"]["content"]
```

```python
# belief_index.py — track recurring patterns
def extract_beliefs(text: str) -> list[str]:
    # Look for strong opinion markers
    markers = [
        "I believe", "I think", "mujhe lagta hai",
        "I always", "I never", "mere hisaab se",
        "I prefer", "I hate", "I love", "meri raay"
    ]
    beliefs = []
    for sentence in text.split("."):
        if any(m.lower() in sentence.lower() for m in markers):
            beliefs.append(sentence.strip())
    return beliefs
```

**Packages to install:**
```bash
pip install chromadb sentence-transformers ollama
```

**Milestone:** Your past conversations are searchable. Ask something and it finds the 5 most relevant things you've previously said about it.

---

### Phase 3 — Retrieval & Reasoning Core

**Goal:** When you ask a question, the system retrieves relevant memories and generates an answer using only those — no internet, no outside knowledge.

**Language:** Python

**What to build:**
- Retriever that combines recency + semantic similarity scoring
- A prompt builder that injects your retrieved memories as context
- Strict guardrail: if no memory found, it says "I don't have your thoughts on this yet"

**Key files:** `retriever.py`, `ranker.py`, `llm_core.py`

```python
# ranker.py — combine recency + relevance score
from datetime import datetime

def rank_results(results: list[dict], query_time: datetime) -> list[dict]:
    for r in results:
        memory_time = datetime.fromisoformat(r["metadata"]["timestamp"])
        age_days = (query_time - memory_time).days
        recency_score = 1 / (1 + age_days * 0.05)   # decays slowly
        r["final_score"] = r["relevance"] * 0.7 + recency_score * 0.3
    return sorted(results, key=lambda x: x["final_score"], reverse=True)
```

```python
# llm_core.py — generate answer strictly from memories
import ollama

SYSTEM_PROMPT = """
You are a digital version of the user. You can ONLY answer using the memories
provided below. If the memories do not contain relevant information, say:
"I haven't shared my thoughts on this yet."

Never use outside knowledge. Never search the internet.
Answer in the same language the question was asked (English / Hindi / Hinglish).
"""

def generate_answer(query: str, memories: list[str], language: str) -> str:
    context = "\n---\n".join(memories)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"""
My memories:
{context}

My question ({language}):
{query}
"""}
    ]
    response = ollama.chat(model="mistral", messages=messages)
    return response["message"]["content"]
```

**Milestone:** Ask "What do I think about discipline?" and get an answer drawn entirely from things you previously said — spoken back to you in your own words.

---

### Phase 4 — Voice Output (Text-to-Speech)

**Goal:** The agent speaks every answer aloud. No reading. Works offline. Handles all three languages.

**Language:** Python

**What to build:**
- TTS engine using Coqui TTS or Piper (fully offline)
- Language router: pick the right voice/model based on detected language
- Audio playback that triggers automatically after each response

**Key files:** `tts_engine.py`, `language_router.py`

```python
# tts_engine.py — offline TTS with Coqui
from TTS.api import TTS
import sounddevice as sd
import soundfile as sf
import tempfile, os

tts_en = TTS("tts_models/en/ljspeech/tacotron2-DDC")
tts_hi = TTS("tts_models/hi/cv/vits")  # Hindi model

def speak(text: str, language: str):
    model = tts_hi if language in ["hindi", "hinglish"] else tts_en
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name
    model.tts_to_file(text=text, file_path=tmp_path)
    data, samplerate = sf.read(tmp_path)
    sd.play(data, samplerate)
    sd.wait()
    os.unlink(tmp_path)
```

```python
# language_router.py — pick language for response
def route_language(query_lang: str, response_text: str) -> str:
    """
    If user asked in Hinglish → respond in Hinglish
    If user asked in Hindi → respond in Hindi
    If user asked in English → respond in English
    """
    return query_lang  # LLM already generates in detected language
```

**Packages to install:**
```bash
pip install TTS sounddevice soundfile
```

**Milestone:** Full loop working. Speak a question → agent finds your memories → speaks the answer back. Everything happens on your device.

---

### Phase 5 — Desktop UI (React + Tauri)

**Goal:** A clean desktop app so you don't have to use the terminal. Push-to-talk button, chat history, memory panel.

**Language:** React (JavaScript) for UI · Rust (auto-handled by Tauri) for desktop shell · Python backend running as a local server via FastAPI

**What to build:**
- FastAPI server wrapping the Python backend
- Tauri desktop app with React frontend
- Voice recording button (push-to-talk)
- Chat window showing conversation history
- Memory panel showing what the agent has learned about you

```python
# api/server.py — FastAPI bridge
from fastapi import FastAPI, UploadFile
from backend.ingest.listener import transcribe_audio
from backend.ingest.preprocessor import preprocess
from backend.memory.store import add_memory, search_memories
from backend.reasoning.llm_core import generate_answer
from backend.output.tts_engine import speak

app = FastAPI()

@app.post("/chat/text")
async def chat_text(body: dict):
    query = body["text"]
    processed = preprocess(query)
    memories = search_memories(query)
    answer = generate_answer(query, memories, processed["language"])
    speak(answer, processed["language"])
    return {"answer": answer, "language": processed["language"]}

@app.post("/chat/voice")
async def chat_voice(audio: UploadFile):
    audio_path = f"/tmp/{audio.filename}"
    with open(audio_path, "wb") as f:
        f.write(await audio.read())
    transcribed = transcribe_audio(audio_path)
    return await chat_text({"text": transcribed["text"]})

@app.post("/memory/add")
async def add(body: dict):
    processed = preprocess(body["text"])
    add_memory(processed["text"], processed)
    return {"status": "saved"}
```

```jsx
// frontend/src/components/VoiceButton.jsx
import { useState } from "react";

export default function VoiceButton({ onResult }) {
  const [recording, setRecording] = useState(false);
  let mediaRecorder;

  const startRecording = async () => {
    setRecording(true);
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    const chunks = [];
    mediaRecorder.ondataavailable = e => chunks.push(e.data);
    mediaRecorder.onstop = async () => {
      const blob = new Blob(chunks, { type: "audio/wav" });
      const form = new FormData();
      form.append("audio", blob, "recording.wav");
      const res = await fetch("http://localhost:8000/chat/voice", {
        method: "POST", body: form
      });
      const data = await res.json();
      onResult(data.answer);
    };
    mediaRecorder.start();
  };

  const stopRecording = () => {
    setRecording(false);
    mediaRecorder?.stop();
  };

  return (
    <button
      onMouseDown={startRecording}
      onMouseUp={stopRecording}
      style={{ background: recording ? "#e24b4a" : "#1d9e75" }}
    >
      {recording ? "Recording..." : "Hold to Speak"}
    </button>
  );
}
```

**Packages to install:**
```bash
# Python
pip install fastapi uvicorn python-multipart

# Node (frontend)
npm create tauri-app personal-ai-agent
cd personal-ai-agent && npm install
```

**Milestone:** A real desktop app. Press a button, speak, hear yourself answer.

---

## 📦 Full Installation Guide

### Prerequisites

- Python 3.10+
- Node.js 18+
- Rust (for Tauri)
- Ollama installed and running
- ~8 GB free disk space for models

### Step 1 — Clone and set up Python backend

```bash
git clone https://github.com/yourname/personal-ai-agent
cd personal-ai-agent/backend

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Step 2 — Download models

```bash
# Pull local LLM
ollama pull mistral

# Whisper model (auto-downloads on first use)
python -c "import whisper; whisper.load_model('medium')"

# TTS model (auto-downloads on first use)
python -c "from TTS.api import TTS; TTS('tts_models/en/ljspeech/tacotron2-DDC')"
```

### Step 3 — Start backend server

```bash
cd backend
uvicorn api.server:app --host 127.0.0.1 --port 8000
```

### Step 4 — Start frontend

```bash
cd frontend
npm install
npm run tauri dev
```

---

## 📋 requirements.txt

```
openai-whisper
lingua-language-detector
chromadb
sentence-transformers
ollama
TTS
sounddevice
soundfile
fastapi
uvicorn
python-multipart
sqlalchemy
python-dotenv
```

---

## 🗓️ Development Timeline (Suggested)

| Phase | What | Estimated Time |
|---|---|---|
| Phase 1 | Data ingestion + language detection | 1–2 weeks |
| Phase 2 | Memory layer + vector DB | 1–2 weeks |
| Phase 3 | Retrieval + reasoning core | 1–2 weeks |
| Phase 4 | Voice output (TTS) | 3–5 days |
| Phase 5 | Desktop UI (React + Tauri) | 2–3 weeks |
| Testing | End-to-end, multilingual QA | 1 week |

---

## 🔒 Privacy

- Everything runs on your device. No data ever leaves your machine.
- No internet connection required after initial model download.
- Your conversations are stored in a local SQLite database and ChromaDB — both plain files on your disk.
- You can delete your memory at any time by deleting the `data/` folder.

---

## 🌐 Language Support

| Language | Input (STT) | Storage | Output (TTS) |
|---|---|---|---|
| English | ✅ Whisper | ✅ | ✅ Coqui EN |
| Hindi | ✅ Whisper | ✅ | ✅ Coqui HI |
| Hinglish | ✅ Whisper + normaliser | ✅ | ✅ EN voice, HI vocabulary |

---

## 💡 Future Ideas

- Emotion tagging (detect mood from your messages over time)
- Daily reflection prompt: agent asks you one question each morning
- Export your "belief map" as a visual graph
- Voice cloning so the agent literally sounds like you
- Mobile version (React Native + Python backend on local network)

---

*Built to be a digital extension of your own mind — not a replacement for it.*
