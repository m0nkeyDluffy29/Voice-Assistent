"""
YouTube Music playback skill — plays songs from YouTube using yt-dlp + mpv.

Voice commands:
    "play [song name]"
    "play [song name] by [artist]"
    "stop music" / "pause music"
"""
import subprocess
import re
import threading
import os
import signal

TRIGGERS = ["play ", "start playing", "put on"]
STOP_TRIGGERS = ["stop music", "pause music", "stop song", "stop the music",
                 "stop playing", "stop the song", "band karo", "music band"]

_current_pid = None
_lock = threading.Lock()


def can_handle(query: str) -> bool:
    q = query.lower().strip()
    if any(t in q for t in STOP_TRIGGERS):
        return True
    # Only handle "play" if it looks like a music request (not a game etc.)
    if any(t in q for t in TRIGGERS):
        # Skip common non-music phrases
        if any(bad in q for bad in ["play chess", "play game", "play with", "play tennis"]):
            return False
        return True
    return False


def handle(query: str, agent_name: str, language: str) -> str:
    q = query.lower().strip()

    # Stop commands
    if any(t in q for t in STOP_TRIGGERS):
        return _stop_music()

    # Extract song name — remove trigger words
    song = q
    for kw in ["can you play", "please play", "play the song", "play song",
               "play the", "start playing", "put on", "play "]:
        song = song.replace(kw, "")
    # Remove trailing filler
    for kw in [" on youtube", " youtube", " for me", " please", " now"]:
        song = song.replace(kw, "")
    song = song.strip(" .,?!")

    if not song or len(song) < 2:
        return "What song would you like to hear?"

    # Verify mpv is installed
    if not _has_command("mpv"):
        return "I need mpv to play music. Install it with: sudo apt install mpv"

    # Verify yt-dlp is installed
    if not _has_command("yt-dlp"):
        return "I need yt-dlp to search YouTube. Install it with: pip install yt-dlp"

    # Resolve the direct audio stream URL ourselves before handing off to mpv.
    # mpv's built-in ytdl_hook lets yt-dlp fall back through several YouTube
    # client types (web, tv, android...) one at a time, which routinely takes
    # 20-30s+ to land on one that works. Forcing the android_vr client here
    # resolves in ~2-3s, so playback starts almost immediately.
    stream_url = _resolve_stream_url(song)
    if not stream_url:
        return f"Couldn't find {song} on YouTube."

    # Stop anything currently playing
    _stop_music()

    # Play in background — don't block conversation
    threading.Thread(target=_play_song, args=(stream_url,), daemon=True).start()

    return f"Playing {song}"


def _has_command(cmd: str) -> bool:
    return subprocess.run(["which", cmd], capture_output=True).returncode == 0


def _resolve_stream_url(song: str) -> str:
    """
    Search YouTube and return a direct playable audio URL.
    Tries the fast android_vr client first (~2-3s); falls back to yt-dlp's
    default multi-client resolution (slower, ~20-30s) if that yields nothing.
    """
    search_query = f"ytsearch1:{song}"

    for args, timeout in (
        (["--extractor-args", "youtube:player_client=android_vr"], 15),
        ([], 30),
    ):
        try:
            result = subprocess.run(
                ["yt-dlp", "-f", "bestaudio", "--no-playlist", *args, "-g", search_query],
                capture_output=True, text=True, timeout=timeout,
            )
            url = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
            if url.startswith("http"):
                return url
        except Exception:
            continue
    return None


def _stop_music() -> str:
    """Kill all mpv processes started by this session."""
    global _current_pid
    with _lock:
        if _current_pid:
            try:
                os.killpg(os.getpgid(_current_pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            _current_pid = None

    # Also kill any orphaned mpv processes with music playback
    subprocess.run(["pkill", "-f", "mpv.*videoplayback"], capture_output=True)
    subprocess.run(["pkill", "-f", "mpv.*ytsearch"], capture_output=True)
    subprocess.run(["pkill", "-f", "mpv.*youtube"], capture_output=True)
    return "Music stopped."


def _play_song(stream_url: str):
    """Play an already-resolved direct audio stream URL in mpv."""
    global _current_pid

    try:
        # stream_url is a direct googlevideo link (resolved in _resolve_stream_url),
        # so mpv doesn't need its own (slow) ytdl_hook resolution here.
        process = subprocess.Popen(
            [
                "mpv",
                "--no-video",           # audio only
                "--really-quiet",       # no console spam
                "--no-terminal",        # don't grab terminal
                stream_url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,       # New process group so we can kill it cleanly
        )

        with _lock:
            _current_pid = process.pid

        # Wait for it — this thread stays alive while music plays
        _, stderr = process.communicate()
        if process.returncode not in (0, None) and stderr:
            print(f"[youtube_music] mpv exited with error: {stderr.decode(errors='ignore').strip()[:300]}")

        with _lock:
            if _current_pid == process.pid:
                _current_pid = None

    except Exception as e:
        print(f"[youtube_music] error: {e}")


def status() -> str:
    """Check if music is currently playing."""
    global _current_pid
    if _current_pid:
        try:
            os.kill(_current_pid, 0)   # Check if process exists
            return "playing"
        except ProcessLookupError:
            _current_pid = None
    return "stopped"