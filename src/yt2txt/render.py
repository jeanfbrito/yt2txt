"""Transcript model and renderers (Markdown is canonical; txt and json derive from it)."""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field

from .youtube import canonical_url


@dataclass
class Transcript:
    id: str
    title: str
    channel: str
    duration_s: int
    upload_date: str
    track: str  # "en/manual", "en/auto", "pt/stt"
    paragraphs: list[tuple[float, str]]
    description: str = ""
    chapters: list[dict] = field(default_factory=list)
    stt_model: str | None = None
    fetched: str = ""

    @property
    def words(self) -> int:
        return sum(len(t.split()) for _, t in self.paragraphs)

    @property
    def url(self) -> str:
        return canonical_url(self.id)


def slug(title: str, n: int = 60) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()
    return s[:n].rstrip("-") or "video"


def stamp(sec: float) -> str:
    sec = int(sec)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def blocks(cues, block_seconds: float, chapters) -> list[tuple[float, str]]:
    """Group cues into paragraphs; break on chapter starts and every block_seconds."""
    bounds = sorted({c.get("start_time", 0) for c in (chapters or [])})
    out, cur, cur_start, next_cut = [], [], None, None
    for t, text in cues:
        if cur_start is None:
            cur_start, next_cut = t, t + block_seconds
        crossed_chapter = any(cur_start < b <= t for b in bounds)
        if cur and (t >= next_cut or crossed_chapter):
            out.append((cur_start, " ".join(cur)))
            cur, cur_start, next_cut = [], t, t + block_seconds
        cur.append(text)
    if cur:
        out.append((cur_start, " ".join(cur)))
    return out


def build(
    meta: dict, cues, lang: str, kind: str, block_seconds: float, stt_model: str | None = None
) -> Transcript:
    chapters = meta.get("chapters") or []
    up = meta.get("upload_date") or ""
    return Transcript(
        id=meta["id"],
        title=meta.get("title", ""),
        channel=meta.get("channel") or meta.get("uploader") or "",
        duration_s=int(meta.get("duration") or 0),
        upload_date=f"{up[:4]}-{up[4:6]}-{up[6:]}" if len(up) == 8 else up,
        track=f"{lang}/{kind}",
        paragraphs=blocks(cues, block_seconds, chapters),
        description=(meta.get("description") or "").strip(),
        chapters=chapters,
        stt_model=stt_model,
        fetched=dt.date.today().isoformat(),
    )


def render_md(t: Transcript) -> str:
    lang, kind = t.track.split("/", 1)
    caption_note = f"{lang} ({kind}, {t.stt_model})" if t.stt_model else f"{lang} ({kind})"
    lines = [
        "---",
        "source: youtube",
        f"id: {t.id}",
        f"url: {t.url}",
        f"title: {json.dumps(t.title)}",
        f"channel: {json.dumps(t.channel)}",
        f"duration_s: {t.duration_s}",
        f"upload_date: {t.upload_date}",
        f"fetched: {t.fetched}",
        f"track: {t.track}",
    ]
    if t.stt_model:
        lines.append(f"stt_model: {t.stt_model}")
    lines += [
        f"words: {t.words}",
        "---",
        "",
        f"# {t.title}",
        "",
        f"{t.channel} · {stamp(t.duration_s)} · {t.url} · captions: {caption_note}",
        "",
    ]
    if t.description:
        lines += ["## Description", ""] + t.description.splitlines()[:40] + [""]
    if t.chapters:
        lines += (
            ["## Chapters", ""]
            + [f"- [{stamp(c.get('start_time', 0))}] {c.get('title', '')}" for c in t.chapters]
            + [""]
        )
    lines += ["## Transcript", ""]
    for start, text in t.paragraphs:
        lines += [f"**[{stamp(start)}]** {text}", ""]
    return "\n".join(lines)


def render_txt(t: Transcript) -> str:
    head = f"{t.title} — {t.channel} — {t.url}"
    body = "\n\n".join(f"[{stamp(s)}] {text}" for s, text in t.paragraphs)
    return f"{head}\n\n{body}\n"


def to_dict(t: Transcript) -> dict:
    return {
        "id": t.id,
        "url": t.url,
        "title": t.title,
        "channel": t.channel,
        "duration_s": t.duration_s,
        "upload_date": t.upload_date,
        "track": t.track,
        "stt_model": t.stt_model,
        "words": t.words,
        "paragraphs": [{"start_s": round(s, 3), "text": text} for s, text in t.paragraphs],
    }


def render_json(t: Transcript) -> str:
    return json.dumps(to_dict(t), ensure_ascii=False, indent=2) + "\n"


_FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)
_PARA_RE = re.compile(r"^\*\*\[(?:(\d+):)?(\d{1,2}):(\d{2})\]\*\* (.*)$", re.M)


def _unstamp(h, m, s) -> float:
    return (int(h) if h else 0) * 3600 + int(m) * 60 + int(s)


def parse_md(text: str) -> Transcript:
    """Rebuild a Transcript from a cached Markdown file written by render_md."""
    m = _FM_RE.match(text)
    if not m:
        raise ValueError("no frontmatter")
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()

    def unq(v: str) -> str:
        try:
            return json.loads(v) if v.startswith('"') else v
        except json.JSONDecodeError:
            return v

    paras = [(_unstamp(h, mm, s), body) for h, mm, s, body in _PARA_RE.findall(text)]
    return Transcript(
        id=fm.get("id", ""),
        title=unq(fm.get("title", "")),
        channel=unq(fm.get("channel", "")),
        duration_s=int(fm.get("duration_s") or 0),
        upload_date=fm.get("upload_date", ""),
        track=fm.get("track", "?"),
        paragraphs=paras,
        stt_model=fm.get("stt_model") or None,
        fetched=fm.get("fetched", ""),
    )
