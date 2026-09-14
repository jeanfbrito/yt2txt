"""yt2txt command line: YouTube URL in, transcript out."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from . import Yt2TxtError, __version__, render, stt, youtube

CACHE_DIR = Path(os.environ.get("YT_TRANSCRIPT_DIR", Path.home() / ".local/share/yt-transcripts"))
DEFAULT_LANGS = "en,en-orig,pt,pt-BR,pt-PT"
DEFAULT_FALLBACK_BROWSER = "chrome"
BOT_CHECK_MARKERS = (
    "sign in to confirm",
    "not a bot",
    "cookies",
    "login required",
    "members-only",
    "age-restricted",
)


def is_bot_check(msg: str) -> bool:
    m = msg.lower()
    return any(k in m for k in BOT_CHECK_MARKERS)


HELP = """\
Examples:
  yt2txt https://youtu.be/ID                 # markdown transcript on stdout
  yt2txt ID --format txt                      # plain text with [mm:ss] paragraphs
  yt2txt ID --format json | jq .paragraphs    # machine-readable
  yt2txt ID --save --out ./transcripts        # cache + copy, print an OK line
  yt2txt ID --stt --fast                      # force local whisper.cpp, all cores
  yt2frame ID 2:30 4:10                       # sister tool: JPEG snapshots at those moments

Captions are used when YouTube has them (manual first, then auto). Otherwise the audio is
downloaded and transcribed locally with whisper.cpp at low priority. If YouTube demands a
sign-in, the fetch is retried once with your browser's cookies (YT2TXT_FALLBACK_BROWSER,
default chrome; set to empty to disable). Set YT2TXT_MODEL, YT2TXT_MODEL_DIR,
YT_TRANSCRIPT_DIR or YT_TRANSCRIPT_COOKIES_BROWSER to change other defaults.
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="yt2txt",
        description="YouTube URL in, transcript out.",
        epilog=HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("videos", nargs="+", help="YouTube URLs or 11-char ids")
    ap.add_argument(
        "--format", choices=["md", "txt", "json"], default="md", help="stdout format (default md)"
    )
    ap.add_argument(
        "--save",
        action="store_true",
        help="write Markdown to the cache and print an OK line instead of the body",
    )
    ap.add_argument("--out", type=Path, help="also copy the Markdown into this directory (implies --save)")
    ap.add_argument("--stt", action="store_true", help="skip captions and transcribe the audio locally")
    ap.add_argument(
        "--model",
        default=stt.DEFAULT_MODEL,
        help=f"whisper.cpp ggml model name (default {stt.DEFAULT_MODEL})",
    )
    ap.add_argument("--language", help="spoken language hint for STT (default: auto-detect)")
    ap.add_argument(
        "--fast",
        action="store_true",
        help="STT with all cores and no nice (default: half the cores, nice 10)",
    )
    ap.add_argument("--langs", default=DEFAULT_LANGS, help="caption language preference order")
    ap.add_argument("--block-seconds", type=float, default=60.0, help="paragraph length in seconds")
    ap.add_argument("--force", action="store_true", help="ignore the cache")
    ap.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        help="pass through to yt-dlp when YouTube demands sign-in",
    )
    ap.add_argument("--quiet", action="store_true", help="no progress on stderr")
    ap.add_argument("--version", action="version", version=f"yt2txt {__version__}")
    a = ap.parse_args(argv)
    if a.out:
        a.save = True
    return a


def cached_file(vid: str) -> Path | None:
    hits = sorted(CACHE_DIR.glob(f"{vid}-*.md"))
    return hits[0] if hits else None


def fetch(vid: str, a: argparse.Namespace, extra: list[str], log) -> render.Transcript:
    url = youtube.canonical_url(vid)
    langs = [x.strip() for x in a.langs.split(",") if x.strip()]
    log(f"{vid}: fetching metadata")
    meta = youtube.metadata(url, extra)
    lang, kind = (None, None) if a.stt else youtube.pick_track(meta, langs)
    with tempfile.TemporaryDirectory(prefix="yt2txt-") as td:
        tmp = Path(td)
        if lang:
            log(f"{vid}: downloading {kind} captions ({lang})")
            cues = youtube.parse_json3(youtube.fetch_json3(url, vid, lang, kind, tmp, extra))
            return render.build(meta, cues, lang, kind, a.block_seconds)
        dur = render.stamp(meta.get("duration") or 0)
        log(
            f"{vid}: no captions, downloading audio ({dur})"
            if not a.stt
            else f"{vid}: downloading audio ({dur})"
        )
        wav = youtube.fetch_audio_wav(url, vid, tmp, extra)
        cues, detected = stt.transcribe(wav, a.model, a.language, a.fast, tmp, log)
        return render.build(meta, cues, detected, "stt", a.block_seconds, stt_model=a.model)


def cookie_args(browser_flag: str | None) -> tuple[list[str], str | None]:
    """yt-dlp cookie flags from CLI/env, plus the browser to fall back to on a bot check."""
    browser = browser_flag or os.environ.get("YT_TRANSCRIPT_COOKIES_BROWSER")
    extra = ["--cookies-from-browser", browser] if browser else []
    fallback = (
        None if browser else (os.environ.get("YT2TXT_FALLBACK_BROWSER", DEFAULT_FALLBACK_BROWSER) or None)
    )
    return extra, fallback


def with_cookie_retry(fn, vid: str, extra: list[str], fallback_browser: str | None, log):
    """Call fn(extra); on a YouTube sign-in / bot check, retry once with browser cookies."""
    try:
        return fn(extra)
    except Yt2TxtError as e:
        if not (fallback_browser and is_bot_check(str(e))):
            raise
        log(f"{vid}: YouTube asked for sign-in, retrying with {fallback_browser} cookies")
        return fn([*extra, "--cookies-from-browser", fallback_browser])


def emit(t: render.Transcript, fmt: str, md_text: str | None = None) -> str:
    if fmt == "md":
        return md_text if md_text is not None else render.render_md(t)
    if fmt == "txt":
        return render.render_txt(t)
    return render.render_json(t)


def main(argv: list[str] | None = None) -> int:
    a = parse_args(argv)
    log = (lambda s: None) if a.quiet else (lambda s: print(s, file=sys.stderr, flush=True))
    extra, fallback_browser = cookie_args(a.cookies_from_browser)

    rc = 0
    bodies: list[str] = []
    json_items: list[dict] = []
    for raw in a.videos:
        try:
            vid = youtube.video_id(raw)
            hit = None if a.force else cached_file(vid)
            if hit:
                md_text = hit.read_text(encoding="utf-8")
                t = render.parse_md(md_text)
                path = hit
                cached = True
            else:
                youtube.require_binary("yt-dlp", "brew install yt-dlp")
                t = with_cookie_retry(
                    lambda ex, v=vid: fetch(v, a, ex, log), vid, extra, fallback_browser, log
                )
                md_text = render.render_md(t)
                path = None
                cached = False
                if a.save:
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    path = CACHE_DIR / f"{vid}-{render.slug(t.title)}.md"
                    path.write_text(md_text, encoding="utf-8")
            if a.save:
                if a.out:
                    a.out.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, a.out / path.name)
                    path = a.out / path.name
                line = f"OK {path} words={t.words} track={t.track} duration={t.duration_s}"
                print(line + (" cached=1" if cached else ""))
            elif a.format == "json":
                json_items.append(render.to_dict(t))
            else:
                bodies.append(emit(t, a.format, md_text))
        except Yt2TxtError as e:
            print(f"FAIL {raw} {e}", file=sys.stderr, flush=True)
            rc = 1
        except KeyboardInterrupt:
            print(f"FAIL {raw} interrupted", file=sys.stderr, flush=True)
            return 130

    if json_items:
        single = len(json_items) == 1 and len(a.videos) == 1
        out = json_items[0] if single else json_items
        sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    elif bodies:
        sys.stdout.write("\n---\n".join(bodies))
        if not bodies[-1].endswith("\n"):
            sys.stdout.write("\n")
    sys.stdout.flush()
    return rc


if __name__ == "__main__":
    sys.exit(main())
