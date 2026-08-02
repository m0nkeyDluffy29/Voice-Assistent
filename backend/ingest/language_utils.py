"""
language_utils.py — Language detection and Hinglish normalisation
Phase 1: Data Ingestion Layer

Handles:
- Detecting whether text is English, Hindi, or Hinglish
- Normalising Hinglish spellings (multiple ways to write the same word)
- Extracting simple entities (names, dates, places) without external APIs
"""

import re
from datetime import datetime
from typing import Literal

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

Language = Literal["english", "hindi", "hinglish", "unknown"]


# ---------------------------------------------------------------------------
# Hinglish vocabulary (common words written in Latin script)
# Add more words as you use the app — this grows over time
# ---------------------------------------------------------------------------

HINGLISH_MARKERS = {
    # Common verbs
    "hai", "hain", "tha", "thi", "the", "hoga", "hogi", "hoge",
    "kar", "karo", "karna", "kiya", "karke", "karta", "karti",
    "ja", "jao", "jata", "jaati", "gaya", "gayi",
    "aa", "aao", "aata", "aati", "aaya", "aayi",
    "ho", "hona", "hua", "hui",
    "de", "dena", "diya", "diyo",
    "le", "lena", "liya",
    "bata", "batao", "batana",
    "bol", "bolo", "bolna", "bola",

    # Common pronouns and particles
    "mein", "main", "mujhe", "mujhko", "mera", "meri", "mere",
    "tum", "tumhe", "tumhara", "tumhari", "tumhare",
    "aap", "aapko", "aapka", "aapki", "aapke",
    "yeh", "ye", "woh", "wo", "isko", "usko", "inhe", "unhe",
    "hum", "hamara", "hamari", "hamare", "humko", "humhe",

    # Postpositions
    "ka", "ki", "ke", "ko", "se", "ne", "par", "pe", "mein",
    "tak", "tak", "wala", "wali", "wale",

    # Common adjectives / adverbs
    "accha", "achha", "acha", "theek", "thik", "sahi", "galat",
    "bahut", "bohot", "thoda", "zyada", "jyada", "kam",
    "abhi", "ab", "pehle", "baad", "phir", "fir",
    "haan", "han", "nahi", "nahin", "nah",
    "kya", "kyun", "kyunki", "kaise", "kab", "kahan", "kaun",

    # Opinion/belief markers (important for belief index later)
    "lagta", "lagti", "sochta", "sochti", "chahta", "chahti",
    "pasand", "napasand", "zaroor", "bilkul", "shayad",

    # Common nouns
    "baat", "kaam", "din", "raat", "log", "dost", "ghar",
    "paise", "paisa", "khana", "pani", "time", "kal", "aaj",
}

# Normalisation map: variant spellings → canonical form
HINGLISH_NORMALISE = {
    "hai na": "hai na",
    "bohot": "bahut",
    "boht": "bahut",
    "thik": "theek",
    "theek hai": "theek hai",
    "achha": "accha",
    "acha": "accha",
    "kyun": "kyun",
    "kyon": "kyun",
    "nahin": "nahi",
    "nah": "nahi",
    "yaar": "yaar",
    "yr": "yaar",
    "bro": "bro",
    "fir": "phir",
    "phir": "phir",
    "matlab": "matlab",
    "mtlb": "matlab",
    "yrr": "yaar",
}


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def detect_language(text: str) -> Language:
    """
    Detect whether text is English, Hindi (Devanagari), or Hinglish.

    Strategy:
    1. If text contains Devanagari characters → Hindi
    2. If text contains enough Hinglish markers → Hinglish
    3. Otherwise → English

    Returns: 'english' | 'hindi' | 'hinglish' | 'unknown'
    """
    if not text or not text.strip():
        return "unknown"

    # Check for Devanagari script (Hindi)
    devanagari_pattern = re.compile(r'[\u0900-\u097F]')
    if devanagari_pattern.search(text):
        return "hindi"

    # Tokenise (simple split, lowercase)
    words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
    if not words:
        return "unknown"

    # Count Hinglish markers
    hinglish_count = sum(1 for w in words if w in HINGLISH_MARKERS)
    hinglish_ratio = hinglish_count / len(words)

    # If more than 15% of words are Hinglish markers → Hinglish
    if hinglish_ratio >= 0.15 or hinglish_count >= 2:
        return "hinglish"

    return "english"


def get_whisper_language_code(lang: Language) -> str | None:
    """
    Map our internal language name to Whisper's language code.
    Returns None for Hinglish (let Whisper auto-detect).
    """
    mapping = {
        "english": "en",
        "hindi": "hi",
        "hinglish": None,   # Auto-detect works best for Hinglish
        "unknown": None,
    }
    return mapping.get(lang)


# ---------------------------------------------------------------------------
# Hinglish normaliser
# ---------------------------------------------------------------------------

def normalise_hinglish(text: str) -> str:
    """
    Normalise common Hinglish spelling variants to a canonical form.
    This helps with consistent storage and matching later.

    Example:
        "yaar bohot accha tha" → "yaar bahut accha tha"
    """
    normalised = text.lower().strip()

    # Replace known variants (longer phrases first to avoid partial matches)
    for variant, canonical in sorted(HINGLISH_NORMALISE.items(), key=lambda x: -len(x[0])):
        normalised = normalised.replace(variant, canonical)

    return normalised


def preprocess_text(text: str, language: Language) -> str:
    """
    Apply language-appropriate text cleaning.
    """
    text = text.strip()

    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)

    if language in ("hinglish",):
        text = normalise_hinglish(text)

    return text


# ---------------------------------------------------------------------------
# Simple entity extraction (no external API needed)
# ---------------------------------------------------------------------------

# Simple patterns — expand as needed
DATE_PATTERNS = [
    r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',         # 12/05/2024
    r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(,?\s+\d{4})?\b',
    r'\b(aaj|kal|parso|pichhle|agle)\b',            # Hindi time words
    r'\b(today|yesterday|tomorrow|last week|next week)\b',
]

NUMBER_PATTERN = re.compile(r'\b\d+(\.\d+)?\b')

OPINION_STARTERS = [
    # English
    r'\bi (think|believe|feel|know|hate|love|prefer|want|need)\b',
    r'\bin my (opinion|view|experience)\b',
    r'\bfor me\b',
    # Hindi / Hinglish
    r'\b(mujhe lagta|mere hisaab|meri raay|main sochta|main chahta|mujhe pasand|mujhe nafrat)\b',
    r'\blagta hai\b',
]


def extract_entities(text: str) -> dict:
    """
    Extract simple entities from text without any external library.

    Returns:
        {
            "dates":    list of date-like strings found
            "numbers":  list of numbers found
            "is_opinion": bool — does this look like a personal opinion?
        }
    """
    lower = text.lower()

    # Dates
    dates = []
    for pattern in DATE_PATTERNS:
        found = re.findall(pattern, lower, re.IGNORECASE)
        if found:
            dates.extend(found if isinstance(found[0], str) else [f[0] for f in found])

    # Numbers
    numbers = [m.group() for m in NUMBER_PATTERN.finditer(text)]

    # Opinion detection
    is_opinion = any(
        re.search(pattern, lower)
        for pattern in OPINION_STARTERS
    )

    return {
        "dates": list(set(dates)),
        "numbers": numbers[:10],    # Cap at 10 to avoid noise
        "is_opinion": is_opinion,
    }


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    samples = [
        "I think discipline matters more than motivation",
        "yaar bahut achha tha woh din, mujhe bahut pasand aaya",
        "मुझे लगता है कि मेहनत करना जरूरी है",
        "Bro theek hai, kal milte hain",
        "The meeting is on 15/08/2024 at 10am",
    ]

    print("=== Language Utils Test ===\n")
    for text in samples:
        lang = detect_language(text)
        entities = extract_entities(text)
        normalised = preprocess_text(text, lang)
        print(f"Input:      {text}")
        print(f"Language:   {lang}")
        print(f"Normalised: {normalised}")
        print(f"Entities:   {entities}")
        print()