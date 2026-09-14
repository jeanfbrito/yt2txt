"""Local speech-to-text through whisper.cpp's `whisper-cli`."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

from . import Yt2TxtError

DEFAULT_MODEL = os.environ.get("YT2TXT_MODEL", "large-v3-turbo-q5_0")
MODEL_DIR = Path(os.environ.get("YT2TXT_MODEL_DIR", Path.home() / ".cache/yt2txt/models"))
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{name}.bin"
INSTALL_HINT = "brew install whisper-cpp"
NICE_LEVEL = 10


def find_whisper_cli() -> str:
    for name in ("whisper-cli", "whisper-cpp"):
        p = shutil.which(name)
        if p:
            return p
    raise Yt2TxtError(f"whisper-cli not found on PATH ({INSTALL_HINT})")


def default_threads(fast: bool) -> int:
    n = os.cpu_count() or 4
    return n if fast else max(1, n // 2)


def model_path(name: str, log=lambda s: None) -> Path:
    """Return the local ggml model file, downloading it on first use."""
    path = MODEL_DIR / f"ggml-{name}.bin"
    if path.exists():
        return path
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    url = MODEL_URL.format(name=name)
    part = path.with_suffix(".bin.part")
    log(f"downloading model {name} from {url}")
    try:
        with urllib.request.urlopen(url) as resp, open(part, "wb") as fh:
            total = int(resp.headers.get("Content-Length") or 0)
            done, last_pct = 0, -1
            while chunk := resp.read(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    if pct // 10 != last_pct // 10:
                        last_pct = pct
                        log(f"  {pct}% ({done // (1 << 20)} MB)")
    except Exception as e:  # noqa: BLE001 - surface any network/fs error as a FAIL
        part.unlink(missing_ok=True)
        raise Yt2TxtError(f"model download failed: {e}") from e
    part.rename(path)
    return path


def build_cmd(
    cli: str, model: Path, wav: Path, out_prefix: Path, language: str | None, threads: int, nice: bool
) -> list[str]:
    cmd = [
        cli,
        "-m",
        str(model),
        "-f",
        str(wav),
        "-t",
        str(threads),
        "-l",
        language or "auto",
        "-oj",
        "-of",
        str(out_prefix),
        "-np",
    ]
    if nice:
        cmd = ["nice", "-n", str(NICE_LEVEL), *cmd]
    return cmd


def parse_whisper_json(path: Path) -> tuple[list[tuple[float, str]], str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    lang = (data.get("result") or {}).get("language") or "und"
    cues = []
    for seg in data.get("transcription", []):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start_ms = (seg.get("offsets") or {}).get("from", 0)
        cues.append((start_ms / 1000.0, text))
    return cues, lang


def transcribe(
    wav: Path, model_name: str, language: str | None, fast: bool, tmp: Path, log=lambda s: None
) -> tuple[list[tuple[float, str]], str]:
    cli = find_whisper_cli()
    model = model_path(model_name, log)
    threads = default_threads(fast)
    out_prefix = tmp / "whisper"
    cmd = build_cmd(cli, model, wav, out_prefix, language, threads, nice=not fast)
    log(f"transcribing with {model_name}, {threads} threads{'' if fast else ', nice ' + str(NICE_LEVEL)}")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or e.stdout or "").strip()[-300:]
        raise Yt2TxtError(f"whisper-cli exit {e.returncode}: {tail}") from e
    out = out_prefix.with_suffix(".json")
    if not out.exists():
        raise Yt2TxtError("whisper-cli produced no json output")
    cues, lang = parse_whisper_json(out)
    if not cues:
        raise Yt2TxtError("whisper-cli produced an empty transcript")
    return cues, lang
