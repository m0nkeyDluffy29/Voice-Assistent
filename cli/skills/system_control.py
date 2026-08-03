"""
System control skill — volume, media playback, brightness.

Voice commands:
    "volume up" / "volume down" / "mute" / "unmute"
    "set volume to 50"
    "pause" / "resume" / "next song" / "previous song"
    "brightness up" / "brightness down"
"""
import subprocess
import re

VOLUME_TRIGGERS   = ["volume", "louder", "quieter", "mute", "unmute"]
MEDIA_TRIGGERS    = ["pause", "resume", "play music", "next song", "previous song",
                     "next track", "previous track", "skip"]
BRIGHT_TRIGGERS   = ["brightness"]


def can_handle(query: str) -> bool:
    q = query.lower()
    return (any(t in q for t in VOLUME_TRIGGERS) or
            any(t in q for t in MEDIA_TRIGGERS) or
            any(t in q for t in BRIGHT_TRIGGERS))


def handle(query: str, agent_name: str, language: str) -> str:
    q = query.lower()

    # Volume
    if "mute" in q and "unmute" not in q:
        _volume_mute(True)
        return "Muted."
    if "unmute" in q:
        _volume_mute(False)
        return "Unmuted."
    if any(w in q for w in ["volume up", "louder", "increase volume"]):
        _volume_change(+10)
        return "Volume up."
    if any(w in q for w in ["volume down", "quieter", "decrease volume", "lower"]):
        _volume_change(-10)
        return "Volume down."
    # "Set volume to 50"
    m = re.search(r"volume (?:to |at )?(\d+)", q)
    if m:
        _volume_set(int(m.group(1)))
        return f"Volume set to {m.group(1)} percent."

    # Media playback
    if any(w in q for w in ["pause", "stop playing"]) and "music" not in q:
        _media_control("pause")
        return "Paused."
    if any(w in q for w in ["resume", "unpause", "continue playing"]):
        _media_control("play")
        return "Resumed."
    if any(w in q for w in ["next song", "next track", "skip"]):
        _media_control("next")
        return "Next track."
    if any(w in q for w in ["previous song", "previous track", "back song"]):
        _media_control("previous")
        return "Previous track."

    # Brightness
    if "brightness up" in q:
        _brightness_change(+10)
        return "Brightness up."
    if "brightness down" in q:
        _brightness_change(-10)
        return "Brightness down."

    return None


def _volume_change(delta: int):
    """Change volume by delta percent (positive = louder)."""
    sign = "+" if delta > 0 else "-"
    try:
        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{sign}{abs(delta)}%"],
            capture_output=True, timeout=3,
        )
    except FileNotFoundError:
        # Fallback: amixer
        subprocess.run(
            ["amixer", "-D", "pulse", "sset", "Master", f"{abs(delta)}%{sign}"],
            capture_output=True, timeout=3,
        )


def _volume_set(percent: int):
    percent = max(0, min(100, percent))
    try:
        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"],
            capture_output=True, timeout=3,
        )
    except FileNotFoundError:
        subprocess.run(
            ["amixer", "-D", "pulse", "sset", "Master", f"{percent}%"],
            capture_output=True, timeout=3,
        )


def _volume_mute(muted: bool):
    state = "1" if muted else "0"
    try:
        subprocess.run(
            ["pactl", "set-sink-mute", "@DEFAULT_SINK@", state],
            capture_output=True, timeout=3,
        )
    except FileNotFoundError:
        subprocess.run(
            ["amixer", "-D", "pulse", "set", "Master", "mute" if muted else "unmute"],
            capture_output=True, timeout=3,
        )


def _media_control(action: str):
    """Uses playerctl (works with Spotify, VLC, mpv, YouTube in browser)."""
    try:
        subprocess.run(["playerctl", action], capture_output=True, timeout=3)
    except FileNotFoundError:
        print("[system_control] Install playerctl for media control: sudo apt install playerctl")


def _brightness_change(delta: int):
    """Uses brightnessctl if available, xbacklight fallback."""
    try:
        current = subprocess.run(
            ["brightnessctl", "g"], capture_output=True, text=True, timeout=3
        )
        max_val = subprocess.run(
            ["brightnessctl", "m"], capture_output=True, text=True, timeout=3
        )
        cur = int(current.stdout.strip())
        mx  = int(max_val.stdout.strip())
        new = max(1, min(mx, cur + int(mx * delta / 100)))
        subprocess.run(["brightnessctl", "s", str(new)], capture_output=True, timeout=3)
    except (FileNotFoundError, ValueError):
        try:
            subprocess.run(
                ["xbacklight", "-inc" if delta > 0 else "-dec", str(abs(delta))],
                capture_output=True, timeout=3,
            )
        except FileNotFoundError:
            pass