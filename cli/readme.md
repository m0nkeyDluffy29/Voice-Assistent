# Flux — Personal AI Agent CLI

An offline JARVIS-style voice assistant that runs entirely on your machine. No cloud, no data leaves your computer.

```
    ╔═══════════════════════════════════════╗
    ║   FLUX · Personal AI Agent CLI        ║
    ║   offline · voice · memory-driven     ║
    ╚═══════════════════════════════════════╝
```

## What it does

- Say **"Flux"** (or any name you pick) → agent greets you and starts listening
- Have a natural conversation — it replies in ~1–2 seconds via voice
- Remembers past conversations across sessions (SQLite + vector memory)
- Works fully **offline** — no internet needed after setup
- Works over SSH — just install and run in any terminal
- Supports English, Hindi, Hinglish

## Requirements

- **Linux** (Ubuntu/Debian tested — should work on any Linux)
- **Python 3.10+**
- **~4GB RAM free** (for Mistral LLM)
- **Microphone** and speakers
- Optional: **wired earphones** for better recording quality

## Install

### 1. System dependencies

```bash
sudo apt update
sudo apt install portaudio19-dev ffmpeg espeak-ng
```

### 2. Install Ollama and pull Mistral

```bash
# Install Ollama (if not already installed)
curl -fsSL https://ollama.com/install.sh | sh

# Pull Mistral (~4GB, one-time download)
ollama pull mistral
```

### 3. Install Flux

```bash
pip install personal-ai-agent
```

Or from source:

```bash
git clone https://github.com/yourusername/personal-ai-agent-cli
cd personal-ai-agent-cli
pip install -e .
```

### 4. Preload Whisper tiny model (~40MB)

```bash
python3 -c "import whisper; whisper.load_model('tiny')"
```

## Usage

### Default — wake word mode

```bash
flux
```

The agent listens continuously. Say its name to start a conversation. Say "stop", "bye", or "exit" to end the conversation and return to wake-word mode.

### Skip the wake word

```bash
flux --chat
```

Jumps straight into conversation mode.

### Text mode (no voice)

```bash
flux --text
```

Type your questions instead of speaking. Useful over SSH or in noisy environments.

### Options

```bash
flux --name Jarvis          # Change agent name for this session
flux --lang hindi           # Force Hindi
flux --lang hinglish        # Hindi-English mix
```

## First launch

The first time you run `flux`, it asks you to name your agent. This is saved to `~/.flux_config` and used on all subsequent launches.

```
First launch — let's name your agent.
Examples: Flux, Nova, Jarvis, Echo, Sage
Agent name: _
```

## How it works

```
    You say "Flux"
         │
         ▼
    [wake word detected]
         │
         ▼
    Flux greets you via TTS
         │
         ▼
    ┌─────── Conversation Loop ────────┐
    │                                   │
    │   You speak → transcribe          │
    │        │                          │
    │        ▼                          │
    │   Search memory + past turns      │
    │        │                          │
    │        ▼                          │
    │   Mistral generates reply         │
    │        │                          │
    │        ▼                          │
    │   Flux speaks reply               │
    │        │                          │
    │        ▼                          │
    │   Save to memory (background)     │
    │        │                          │
    │        └── loop ──┐               │
    │                   │               │
    └───── say "stop" ──┘               │
                        ▼               │
              Back to wake word         │
```

## Performance

| Step                         | Time               |
| ---------------------------- | ------------------ |
| Whisper transcription (tiny) | ~0.3s              |
| Memory retrieval             | ~0.2s              |
| Mistral inference            | ~1-2s              |
| TTS playback                 | starts immediately |
| **Total per turn**           | **~1.5-2.5s**      |

Compare to the browser version: **3-5s per turn**.

## Troubleshooting

**"No module named sounddevice"**

```bash
sudo apt install portaudio19-dev
pip install sounddevice
```

**"espeak-ng: command not found"**

```bash
sudo apt install espeak-ng
```

**"Cannot connect to Ollama"**

```bash
# Check Ollama is running
ollama list

# If not, start it
ollama serve
```

**Wake word not detecting**

- Speak clearly, close to the mic
- Try shorter names (Flux, Nova) rather than long ones
- Use `--chat` mode instead of wake word

**Voice sounds robotic**
For better quality, install Piper TTS:

```bash
pip install piper-tts
# Then modify flux.py to prefer Piper (see docs)
```

## Files

```
personal-ai-agent-cli/
├── flux.py              # Main CLI (single file — ~450 lines)
├── pyproject.toml       # Package config
├── requirements.txt     # Python deps
└── README.md
```

Config and data live in your project directory:

```
your-project/
├── data/
│   ├── memory.db          # SQLite conversations + memories
│   └── chroma_db/         # Vector embeddings
├── ~/.flux_config         # Agent name preference
```

## License

MIT
