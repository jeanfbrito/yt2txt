"""yt2frame command line: JPEG snapshots of a YouTube video at given timestamps."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import Yt2TxtError, __version__, frames, render, youtube
from .cli import CACHE_DIR, cookie_args, with_cookie_retry

HELP = """\
Examples:
  yt2frame https://youtu.be/ID 2:30                # one JPEG, path printed as a FRAME line
  yt2frame ID 0:45 3:20 4:55 --out ./frames        # several moments in one call
  yt2frame ID 150 --format json                    # machine-readable

Nothing close to a full download happens: yt-dlp resolves a direct stream URL and ffmpeg
seeks into it, reading only the bytes around each requested frame. Use yt2txt for the
transcript, pick the timestamps worth seeing, then call yt2frame with all of them at once.
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="yt2frame",
        description="Snapshot a YouTube video at given timestamps.",
        epilog=HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("video", help="YouTube URL or 11-char id")
    ap.add_argument("times", nargs="+", metavar="TIME", help="seconds, mm:ss or h:mm:ss")
    ap.add_argument("--out", type=Path, help=f"directory for the JPEGs (default {CACHE_DIR / 'frames'})")
    ap.add_argument(
        "--height",
        type=int,
        default=frames.DEFAULT_HEIGHT,
        help=f"max frame height in px (default {frames.DEFAULT_HEIGHT})",
    )
    ap.add_argument(
        "--format", choices=["lines", "json"], default="lines", help="stdout format (default lines)"
    )
    ap.add_argument("--force", action="store_true", help="re-grab even if the file exists")
    ap.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        help="pass through to yt-dlp when YouTube demands sign-in",
    )
    ap.add_argument("--quiet", action="store_true", help="no progress on stderr")
    ap.add_argument("--version", action="version", version=f"yt2frame {__version__}")
    return ap.parse_args(argv)


def snapshot(
    vid: str,
    times: list[float],
    out_dir: Path,
    height: int,
    force: bool,
    extra: list[str],
    fallback_browser: str | None,
    log,
) -> list[dict]:
    """Grab one JPEG per timestamp; returns one dict per frame for FRAME lines / json."""
    results, stream = [], None
    for t in times:
        path = out_dir / frames.frame_name(vid, t)
        cached = path.exists() and not force
        if not cached:
            if stream is None:
                log(f"{vid}: resolving stream url")
                stream = with_cookie_retry(
                    lambda ex: frames.stream_url(youtube.canonical_url(vid), ex, height),
                    vid,
                    extra,
                    fallback_browser,
                    log,
                )
            log(f"{vid}: grabbing frame at {render.stamp(t)}")
            frames.grab_frame(stream, t, path)
        dims = frames.dimensions(path)
        results.append(
            {
                "id": vid,
                "t": t,
                "path": str(path),
                "width": dims[0] if dims else None,
                "height": dims[1] if dims else None,
                "cached": cached,
            }
        )
    return results


def main(argv: list[str] | None = None) -> int:
    a = parse_args(argv)
    log = (lambda s: None) if a.quiet else (lambda s: print(s, file=sys.stderr, flush=True))
    extra, fallback_browser = cookie_args(a.cookies_from_browser)
    out_dir = a.out if a.out else CACHE_DIR / "frames"
    try:
        vid = youtube.video_id(a.video)
        times = [frames.parse_timestamp(x) for x in a.times]
        youtube.require_binary("yt-dlp", "brew install yt-dlp")
        results = snapshot(vid, times, out_dir, a.height, a.force, extra, fallback_browser, log)
    except Yt2TxtError as e:
        print(f"FAIL {a.video} {e}", file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        print(f"FAIL {a.video} interrupted", file=sys.stderr, flush=True)
        return 130
    if a.format == "json":
        sys.stdout.write(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    else:
        for f in results:
            size = f"{f['width']}x{f['height']}" if f["width"] else "?x?"
            print(f"FRAME {f['path']} t={f['t']:g} {size}" + (" cached=1" if f["cached"] else ""))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
