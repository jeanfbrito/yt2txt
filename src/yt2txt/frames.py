"""Single-frame snapshots at given timestamps, without downloading the whole video.

yt-dlp resolves a direct stream URL for a video-only format; ffmpeg seeks into that URL with
HTTP range requests and decodes one frame. Typically well under a second per frame.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import Yt2TxtError
from .youtube import require_binary

DEFAULT_HEIGHT = 720
_TS_RE = re.compile(r"^(?:(\d+):)?(?:(\d{1,2}):)?(\d{1,2}(?:\.\d+)?)$")


def parse_timestamp(s: str) -> float:
    """'2:30' -> 150.0, '1:02:03' -> 3723.0, '90' or '90.5' -> seconds."""
    s = s.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        return float(s)
    m = _TS_RE.match(s)
    if not m:
        raise Yt2TxtError(f"bad timestamp {s!r}; use seconds, mm:ss or h:mm:ss")
    a, b, c = m.groups()
    if b is None:  # mm:ss
        return int(a) * 60 + float(c)
    return int(a) * 3600 + int(b) * 60 + float(c)


def frame_name(vid: str, t: float) -> str:
    t = int(t)
    return f"{vid}-{t // 3600:02d}{(t % 3600) // 60:02d}{t % 60:02d}.jpg"


def stream_url(url: str, extra: list[str], height: int = DEFAULT_HEIGHT) -> str:
    fmt = f"bestvideo[height<={height}][ext=mp4]/bestvideo[height<={height}]/best[height<={height}]/best"
    cmd = ["yt-dlp", "-g", "-f", fmt, "--no-warnings", *extra, url]
    try:
        out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    except subprocess.CalledProcessError as e:
        raise Yt2TxtError(f"yt-dlp exit {e.returncode}: {(e.stderr or '').strip()[-300:]}") from e
    lines = [x for x in out.splitlines() if x.strip()]
    if not lines:
        raise Yt2TxtError("yt-dlp returned no stream url")
    return lines[0]


def ffmpeg_cmd(stream: str, t: float, out: Path) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{t:.3f}",
        "-i",
        stream,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        "-y",
        str(out),
    ]


def dimensions(path: Path) -> tuple[int, int] | None:
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        w, h = out.split(",")[:2]
        return int(w), int(h)
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return None


def grab_frame(stream: str, t: float, out: Path) -> Path:
    require_binary("ffmpeg", "brew install ffmpeg")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(ffmpeg_cmd(stream, t, out), check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or "").strip()
        out.unlink(missing_ok=True)
        if "received no packets" in err or "Nothing was written" in err:
            raise Yt2TxtError(f"no frame at {t:g}s (past the end of the video?)") from e
        raise Yt2TxtError(f"ffmpeg exit {e.returncode}: {err[-300:]}") from e
    if not out.exists() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        raise Yt2TxtError(f"no frame at {t:g}s (past the end of the video?)")
    return out
