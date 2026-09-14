"""YouTube access via yt-dlp: metadata, caption tracks, audio download."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from . import Yt2TxtError

ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})|^([A-Za-z0-9_-]{11})$")


def video_id(s: str) -> str:
    m = ID_RE.search(s.strip())
    if not m:
        raise Yt2TxtError(f"cannot find a YouTube video id in: {s}")
    return m.group(1) or m.group(2)


def canonical_url(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


def require_binary(name: str, install_hint: str) -> str:
    path = shutil.which(name)
    if not path:
        raise Yt2TxtError(f"{name} not found on PATH ({install_hint})")
    return path


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or "").strip()[-300:]
        raise Yt2TxtError(f"{cmd[0]} exit {e.returncode}: {tail}") from e


def metadata(url: str, extra: list[str]) -> dict:
    out = _run(["yt-dlp", "-J", "--skip-download", "--no-warnings", *extra, url]).stdout
    return json.loads(out)


def pick_track(meta: dict, langs: list[str]) -> tuple[str | None, str | None]:
    """Return (lang, kind) preferring manual subtitles, then auto captions, in `langs` order."""
    subs = meta.get("subtitles") or {}
    auto = meta.get("automatic_captions") or {}
    for lang in langs:
        if lang in subs:
            return lang, "manual"
    for lang in langs:
        if lang in auto:
            return lang, "auto"
    if subs:
        return next(iter(subs)), "manual"
    if auto:
        return next(iter(auto)), "auto"
    return None, None


def fetch_json3(url: str, vid: str, lang: str, kind: str, tmp: Path, extra: list[str]) -> Path:
    flag = "--write-subs" if kind == "manual" else "--write-auto-subs"
    _run(
        [
            "yt-dlp",
            "--skip-download",
            "--no-warnings",
            *extra,
            flag,
            "--sub-langs",
            lang,
            "--sub-format",
            "json3",
            "-o",
            str(tmp / "%(id)s.%(ext)s"),
            url,
        ]
    )
    cands = sorted(tmp.glob(f"{vid}*.json3"))
    if not cands:
        raise Yt2TxtError(f"yt-dlp wrote no json3 track for lang={lang} kind={kind}")
    return cands[0]


def parse_json3(path: Path) -> list[tuple[float, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cues = []
    for ev in data.get("events", []):
        if ev.get("aAppend"):
            continue
        segs = ev.get("segs") or []
        text = "".join(s.get("utf8", "") for s in segs)
        text = re.sub(r"\s+", " ", text).strip()
        if not text or text == "[Music]":
            continue
        cues.append((ev.get("tStartMs", 0) / 1000.0, text))
    return cues


def fetch_audio_wav(url: str, vid: str, tmp: Path, extra: list[str]) -> Path:
    """Download best audio and convert to 16 kHz mono 16-bit WAV (what whisper-cli reads)."""
    require_binary("ffmpeg", "brew install ffmpeg")
    _run(
        [
            "yt-dlp",
            "--no-warnings",
            *extra,
            "-f",
            "bestaudio/best",
            "-x",
            "--audio-format",
            "wav",
            "--postprocessor-args",
            "ffmpeg:-ar 16000 -ac 1 -c:a pcm_s16le",
            "-o",
            str(tmp / "%(id)s.%(ext)s"),
            url,
        ]
    )
    cands = sorted(tmp.glob(f"{vid}*.wav"))
    if not cands:
        raise Yt2TxtError("yt-dlp wrote no wav file")
    return cands[0]
