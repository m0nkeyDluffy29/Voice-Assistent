"""
YouTube Music playback skill.
Uses yt-dlp to search and mpv/vlc to play.

Voice commands:
    "play [song name]"
    "play [song name] on youtube"
    "stop music" / "pause music" / "next"
"""
import subprocess
import re
import threading
from pathlib import Path

TRIGGERS = ["play ", "music", "song", "youtube"]
STOP_TRIGGERS = ["stop music", "pause music", "stop song", "pause song", "stop playing"]

# Track the currently playing process
_current_process = None


def can_handle(query: str) -> bool:
    q = query.lower().strip()
    return any(t in q for t in TRIGGERS) or any(t in q for t in STOP_TRIGGERS)


def handle(query: str, agent_name: str, language: str) -> str:
    global _current_process
    q = query.lower().strip()

    # Handle stop commands
    if any(t in q for t in STOP_TRIGGERS):
        return _stop_music()

    # Extract song name — remove "play", "song", "on youtube", etc.
    song = q
    for kw in ["play ", "on youtube", "youtube", "the song", "song", "for me", "please"]:
        song = song.replace(kw, "")
    song = song.strip()

    if not song or len(song) < 2:
        return "What song would you like to hear?"

    # Stop anything currently playing
    _stop_music()

    # Play in background thread so voice loop continues
    threading.Thread(target=_play_song, args=(song,), daemon=True).start()

    return f"Playing {song}"


def _stop_music() -> str:
    global _current_process
    if _current_process and _current_process.poll() is None:
        _current_process.terminate()
        _current_process = None
        return "Music stopped"

    # Also try killing any lingering mpv/vlc
    subprocess.run(["pkill", "-f", "mpv"], capture_output=True)
    subprocess.run(["pkill", "-f", "vlc"], capture_output=True)
    return "Music stopped"


def _play_song(song: str):
    global _current_process
    try:
        # yt-dlp search: ytsearch1: gives first result
        search_query = f"ytsearch1:{song}"

        # Prefer mpv (lightweight), fall back to vlc
        player = None
        for p in ["mpv", "vlc", "cvlc"]:
            if subprocess.run(["which", p], capture_output=True).returncode == 0:
                player = p
                break

        if not player:
            print("[youtube_music] No player found. Install: sudo apt install mpv")
            return

        if player == "mpv":
            # mpv can handle yt-dlp URLs directly
            _current_process = subprocess.Popen(
                ["mpv", "--no-video", "--really-quiet", search_query],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            # For VLC, we need to fetch the URL first with yt-dlp
            result = subprocess.run(
                ["yt-dlp", "-f", "bestaudio", "-g", search_query],
                capture_output=True, text=True, timeout=15,
            )
            url = result.stdout.strip().split("\n")[0]
            if url:
                _current_process = subprocess.Popen(
                    [player, "--intf", "dummy", "--no-video", url],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
    except Exception as e:
        print(f"[youtube_music] Error playing '{song}': {e}")