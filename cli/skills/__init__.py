"""
Flux Skills — modular voice command handlers.

Each skill implements:
    - TRIGGERS: list of keywords that activate the skill
    - can_handle(query: str) -> bool
    - handle(query: str, agent_name: str, language: str) -> str

The main flux loop tries each skill first. If none match, falls back to LLM.
"""
from . import youtube_music, weather, system_control, calculator

# Register all skills — order matters (first match wins)
SKILLS = [
    system_control,   # Volume/pause first (short commands)
    youtube_music,    # Music playback
    weather,          # Weather queries
    calculator,       # Math + unit conversion (last so LLM handles ambiguous questions)
]


def try_handle(query: str, agent_name: str = "Flux", language: str = "english"):
    """
    Try each skill in order. Returns (handled: bool, response: str).
    If no skill matches, returns (False, None) and main loop falls back to LLM.
    """
    for skill in SKILLS:
        try:
            if skill.can_handle(query):
                response = skill.handle(query, agent_name, language)
                if response:
                    return True, response
        except Exception as e:
            print(f"[skill error] {skill.__name__}: {e}")
            continue
    return False, None