#!/bin/bash
# install.sh — one-command installer for Flux CLI

set -e

echo "╔════════════════════════════════════════╗"
echo "║   Flux CLI installer                    ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Detect OS
if ! command -v apt &> /dev/null; then
    echo "⚠  This installer supports Debian/Ubuntu only."
    echo "   On other systems, install manually:"
    echo "   - portaudio, ffmpeg, espeak-ng"
    echo "   - Then: pip install -e ."
    exit 1
fi

echo "[1/5] Installing system dependencies (needs sudo)..."
sudo apt update
sudo apt install -y portaudio19-dev ffmpeg espeak-ng python3-pip python3-venv

echo ""
echo "[2/5] Checking Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "     Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

echo ""
echo "[3/5] Pulling Mistral model (~4GB, one time)..."
ollama pull mistral

echo ""
echo "[4/5] Installing Python package..."
pip install -e . --break-system-packages 2>/dev/null || pip install -e .

echo ""
echo "[5/5] Preloading Whisper tiny model..."
python3 -c "import whisper; whisper.load_model('tiny')"

echo ""
echo "╔════════════════════════════════════════╗"
echo "║   ✓ Installation complete!              ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "Try it now:"
echo "  flux              # wake word mode"
echo "  flux --chat       # direct conversation"
echo "  flux --text       # text mode"
echo ""