"""
language_router.py — Language and voice routing for TTS output
Phase 4: Voice Output Layer

Decides which language/voice to use for the spoken response based on:
  1. The language of the query
  2. The language detected in the generated answer
  3. User preferences (configurable)

Also handles text preprocessing before TTS:
  - Removes markdown formatting (bold, bullets, headers)
  - Splits long answers into speakable chunks
  - Handles mixed Devanagari + Latin (Hinglish edge cases)
  - Removes things that sound bad when read aloud (URLs, IDs, brackets)
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Language routing rules
# ---------------------------------------------------------------------------

LANGUAGE_VOICE_MAP = {
    "english":  "english",
    "hindi":    "hindi",
    "hinglish": "hinglish",
    "unknown":  "english",    # Default fallback
}

# If the answer contains Devanagari, always route to hindi voice
DEVANAGARI_PATTERN = re.compile(r'[\u0900-\u097F]')


def route_language(query_language: str, answer_text: str) -> str:
    """
    Determine which TTS voice to use for the answer.

    Rules:
    1. If answer has Devanagari script → hindi voice
    2. Otherwise → match the query language
    3. Unknown → english

    Args:
        query_language: Detected language of the user's question
        answer_text:    The generated answer text

    Returns:
        TTS language key: 'english' | 'hindi' | 'hinglish'
    """
    # Override to hindi if answer contains Devanagari
    if DEVANAGARI_PATTERN.search(answer_text):
        return "hindi"

    return LANGUAGE_VOICE_MAP.get(query_language, "english")


# ---------------------------------------------------------------------------
# Text cleaning for TTS
# ---------------------------------------------------------------------------

def clean_for_tts(text: str) -> str:
    """
    Preprocess text so it sounds natural when spoken.

    Removes:
    - Markdown formatting (**bold**, *italic*, ##headers, bullet points)
    - Brackets and content inside them that sounds odd spoken aloud
    - URLs
    - Long IDs (UUIDs etc.)
    - Excessive whitespace and newlines
    - Emoji characters (TTS engines can't pronounce them)

    Normalises:
    - Multiple spaces → single space
    - Multiple newlines → sentence pause (period)
    """
    if not text:
        return ""

    # Remove markdown headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Remove bold/italic markers
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', text)

    # Remove bullet points and numbered lists
    text = re.sub(r'^\s*[-*•]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'www\.\S+', '', text)

    # Remove content in square brackets [like this]
    text = re.sub(r'\[(?:MEMORY|BELIEF|SUMMARY)[^\]]*\]', '', text)
    text = re.sub(r'\[[^\]]{0,30}\]', '', text)   # Short bracket content only

    # Remove UUIDs and long hex strings
    text = re.sub(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', '', text)

    # Remove emojis (basic range)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[\U00002702-\U000027B0]', '', text)
    text = re.sub(r'[\U0001F600-\U0001F64F]', '', text)
    text = re.sub(r'[\U0001F300-\U0001F5FF]', '', text)

    # Convert multiple newlines into a period (natural pause)
    text = re.sub(r'\n{2,}', '. ', text)
    text = re.sub(r'\n', ' ', text)

    # Fix multiple spaces
    text = re.sub(r'\s{2,}', ' ', text)

    # Fix multiple periods
    text = re.sub(r'\.{2,}', '.', text)

    # Remove leading/trailing whitespace
    text = text.strip()

    # Ensure ends with punctuation (sounds more complete)
    if text and text[-1] not in '.!?।':
        text += '.'

    return text


# ---------------------------------------------------------------------------
# Chunker — split long answers into speakable pieces
# ---------------------------------------------------------------------------

def chunk_for_speech(text: str, max_chars: int = 250) -> list:
    """
    Split long text into chunks that each work as a complete
    spoken sentence or paragraph.

    TTS engines perform better on shorter inputs — this avoids
    awkward pauses mid-sentence or cut-off speech.

    Args:
        text:      Clean text to chunk
        max_chars: Max characters per chunk

    Returns:
        List of text chunks, each <= max_chars
    """
    if len(text) <= max_chars:
        return [text]

    # Split on sentence boundaries first
    sentence_endings = re.compile(r'(?<=[.!?।])\s+')
    sentences = sentence_endings.split(text)

    chunks  = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            # If single sentence is still too long, split on comma
            if len(sentence) > max_chars:
                parts = re.split(r',\s*', sentence)
                sub_chunk = ""
                for part in parts:
                    if len(sub_chunk) + len(part) + 2 <= max_chars:
                        sub_chunk = f"{sub_chunk}, {part}".strip(", ")
                    else:
                        if sub_chunk:
                            chunks.append(sub_chunk)
                        sub_chunk = part
                if sub_chunk:
                    chunks.append(sub_chunk)
                current = ""
            else:
                current = sentence

    if current:
        chunks.append(current)

    return [c for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# Full pipeline: route + clean + chunk
# ---------------------------------------------------------------------------

def prepare_for_speech(
    answer_text:    str,
    query_language: str,
) -> dict:
    """
    Full preprocessing pipeline for a TTS-ready answer.

    Args:
        answer_text:    Raw answer from llm_core.ask()
        query_language: Language of the original question

    Returns:
        {
            "voice_language": str   — which TTS voice to use
            "clean_text":     str   — full cleaned text
            "chunks":         list  — list of speakable chunks
            "chunk_count":    int
        }
    """
    voice_language = route_language(query_language, answer_text)
    clean_text     = clean_for_tts(answer_text)
    chunks         = chunk_for_speech(clean_text)

    return {
        "voice_language": voice_language,
        "clean_text":     clean_text,
        "chunks":         chunks,
        "chunk_count":    len(chunks),
    }


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    samples = [
        ("**I believe** that discipline is key.\n\n- Wake up early\n- Work consistently\n\nThis is what drives me.", "english"),
        ("Yaar, mujhe lagta hai ki **consistency** bahut zaroor hai.", "hinglish"),
        ("मुझे लगता है कि परिवार सबसे पहले आता है। बाकी सब बाद में।", "hindi"),
        ("I think about this a lot. The truth is, motivation fades but discipline stays. I've seen this in my own life when I tried to build habits. The ones that stuck were the ones I didn't rely on feeling good about.", "english"),
    ]

    print("=== Language Router Test ===\n")
    for text, lang in samples:
        result = prepare_for_speech(text, lang)
        print(f"Input lang: {lang}")
        print(f"Voice:      {result['voice_language']}")
        print(f"Clean:      {result['clean_text'][:100]}")
        print(f"Chunks:     {result['chunk_count']}")
        for i, c in enumerate(result["chunks"], 1):
            print(f"  [{i}] {c}")
        print()