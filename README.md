# yt2txt

YouTube URL in, transcript out. Plus `yt2frame`, a sister command that snapshots the video at
the moments you choose. Built for humans in a terminal and for AI agents that shell out.

```sh
yt2txt https://youtu.be/PcpkBzcRdSU --format txt      # read the talk
yt2frame PcpkBzcRdSU 0:45 3:20 4:55                     # see what was on screen at those moments
```

- **Captions first.** When YouTube has captions, `yt2txt` uses them (manual first, then auto)
  via `yt-dlp`. Seconds per video, no media download.
- **Local speech-to-text fallback.** When a video has no captions, the audio is downloaded and
  transcribed on your machine with [whisper.cpp](https://github.com/ggml-org/whisper.cpp).
  Nothing is uploaded anywhere. No API key.
- **Stays out of your way.** Local transcription runs at low priority on half the cores, one
  video at a time. `--fast` when the machine is free.
- **One output shape** regardless of source: timestamped Markdown (canonical), plain text, or
  JSON. Transcripts are cached so a second call is instant.
- **Frames without the video.** `yt2frame` resolves a direct stream URL and lets ffmpeg seek into
  it with HTTP range requests, so a 720p JPEG takes well under a second.
- **Agent-ready.** Clean stdout, progress on stderr, one-line results, meaningful exit codes, and
  a Claude Code skill in this repo that teaches the transcript-then-frames loop.

## Contents

- [Requirements](#requirements)
- [Install](#install)
- [yt2txt](#yt2txt-1)
- [yt2frame](#yt2frame)
- [How it works](#how-it-works)
- [Output formats](#output-formats)
- [Agent contract](#agent-contract)
- [Configuration](#configuration)
- [Models and machine load](#models-and-machine-load)
- [Cookies and YouTube's bot check](#cookies-and-youtubes-bot-check)
- [Cache layout](#cache-layout)
- [Claude Code skill](#claude-code-skill)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Limitations and non-goals](#limitations-and-non-goals)
- [License](#license)

## Requirements

- macOS on Apple Silicon (whisper.cpp uses Metal; captions and frames also work elsewhere).
- [Homebrew](https://brew.sh) and [uv](https://docs.astral.sh/uv/).
- `yt-dlp`, `ffmpeg`, `whisper-cpp`. The installer adds any that are missing.
- Python 3.11 or newer (uv manages it for the tool).

## Install

```sh
git clone <repo-url> ~/Github/yt2txt
cd ~/Github/yt2txt
./install.sh
```

`install.sh` is idempotent. It:

1. installs missing Homebrew dependencies (`yt-dlp`, `ffmpeg`, `whisper-cpp`),
2. installs the `yt2txt` and `yt2frame` commands with `uv tool install`,
3. links `skill/yt-transcript` into `~/.claude/skills/` for Claude Code.

Re-run it after pulling changes. `make uninstall` removes the uv tool and the skill link.

The first local transcription downloads the default model, `ggml-large-v3-turbo-q5_0.bin`
(574 MB), into `~/.cache/yt2txt/models/`. Nothing else is downloaded up front.

## yt2txt

```
yt2txt URL_OR_ID [URL_OR_ID ...] [options]
```

| Option | Default | Meaning |
|---|---|---|
| `--format md\|txt\|json` | `md` | What goes to stdout |
| `--save` | off | Write Markdown to the cache and print an `OK` line instead of the body |
| `--out DIR` | unset | Also copy the Markdown into `DIR` (implies `--save`) |
| `--stt` | off | Skip captions and transcribe the audio locally |
| `--model NAME` | `large-v3-turbo-q5_0` | whisper.cpp ggml model name (see [Models](#models-and-machine-load)) |
| `--language xx` | auto | Spoken-language hint for local transcription |
| `--fast` | off | Local transcription with all cores at normal priority |
| `--langs a,b,c` | `en,en-orig,pt,pt-BR,pt-PT` | Caption language preference, in order |
| `--block-seconds N` | `60` | Paragraph length in the rendered transcript |
| `--force` | off | Ignore the cache |
| `--cookies-from-browser B` | unset | Pass your browser's cookies to yt-dlp from the start |
| `--quiet` | off | No progress on stderr |

Examples:

```sh
yt2txt https://youtu.be/VIDEO_ID                  # Markdown on stdout
yt2txt VIDEO_ID --format txt                      # [mm:ss] paragraphs, easy to read
yt2txt VIDEO_ID --format json | jq '.paragraphs'  # machine-readable
yt2txt VIDEO_ID --save --out ./transcripts        # cache + project copy, prints an OK line
yt2txt VIDEO_ID --stt                             # ignore captions, transcribe locally
yt2txt VIDEO_ID --stt --fast --language pt        # all cores, Portuguese hint
yt2txt VIDEO_ID --model small-q5_1                # lighter, less accurate model (190 MB)
yt2txt ID1 ID2 ID3 --save                         # several videos, one OK line each
```

Track selection: manual subtitles in `--langs` order, then auto captions in `--langs` order, then
any manual, then any auto, then local transcription. `en-orig` is YouTube's untranslated auto
track and is usually the cleanest auto option.

## yt2frame

```
yt2frame URL_OR_ID TIME [TIME ...] [options]
```

| Option | Default | Meaning |
|---|---|---|
| `TIME` | | Seconds (`150`), `mm:ss` (`2:30`) or `h:mm:ss` (`1:02:03`); as many as you like |
| `--out DIR` | `~/.local/share/yt-transcripts/frames` | Where the JPEGs go |
| `--height N` | `720` | Maximum frame height in pixels |
| `--format lines\|json` | `lines` | What goes to stdout |
| `--force` | off | Re-grab even if the file exists |
| `--cookies-from-browser B` | unset | Pass your browser's cookies to yt-dlp from the start |
| `--quiet` | off | No progress on stderr |

Examples:

```sh
yt2frame VIDEO_ID 2:30                            # one frame
yt2frame VIDEO_ID 0:45 3:20 4:55 --out ./frames   # several moments in one call
yt2frame VIDEO_ID 150 --format json               # machine-readable
```

Output, one line per frame in the order requested:

```
FRAME ./frames/PcpkBzcRdSU-000045.jpg t=45 1280x720
FRAME ./frames/PcpkBzcRdSU-000320.jpg t=200 1280x720
FRAME ./frames/PcpkBzcRdSU-000455.jpg t=295 1280x720 cached=1
```

The stream URL is resolved once per call, so batching timestamps is cheap. A frame that lands on
a fade or a cut can be black; nudge the time by a second or two. Requesting a time past the end
of the video fails with `no frame at Ns (past the end of the video?)`.

## How it works

```
yt2txt URL
  │
  ├─ cached <id>-*.md in the cache dir?  ──yes──▶ render requested format
  │
  ├─ yt-dlp -J  (metadata: title, duration, chapters, caption tracks)
  │
  ├─ caption track found and not --stt?
  │     yes ──▶ yt-dlp --write-subs/--write-auto-subs --sub-format json3
  │              parse cues ──▶ paragraphs (60 s blocks, split at chapters)
  │
  │     no  ──▶ yt-dlp -x --audio-format wav  (16 kHz mono 16-bit, what whisper-cli reads)
  │              whisper-cli -m ggml-<model>.bin -t <cores/2> -l auto -oj   (under nice -n 10)
  │              parse segments ──▶ paragraphs
  │
  └─ render Markdown (canonical) ──▶ stdout, or --save to cache (+ --out copy)

yt2frame URL T1 T2 ...
  │
  ├─ yt-dlp -g -f "bestvideo[height<=720][ext=mp4]/..."   (direct stream URL, once)
  │
  └─ per T:  ffmpeg -ss T -i <stream-url> -frames:v 1 out.jpg   (HTTP range seek, one frame)
```

If YouTube answers any step with its sign-in / bot check, the step is retried once with your
browser's cookies (see [Cookies](#cookies-and-youtubes-bot-check)).

## Output formats

**Markdown** (canonical, what the cache stores):

```markdown
---
source: youtube
id: PcpkBzcRdSU
url: https://www.youtube.com/watch?v=PcpkBzcRdSU
title: "Procedural Animation in 5 Minutes | devlog 1"
channel: "Benjamin Blodgett"
duration_s: 325
upload_date: 2022-05-01
fetched: 2026-09-14
track: en/auto
words: 1039
---

# Procedural Animation in 5 Minutes | devlog 1

Benjamin Blodgett · 05:25 · https://www.youtube.com/watch?v=PcpkBzcRdSU · captions: en (auto)

## Description
(first 40 lines of the video description)

## Chapters
- [00:00] Intro
- [01:08] Part 2

## Transcript

**[00:00]** For aesthetic purposes, I will refer to two practical groupings of legs ...

**[01:02]** ...
```

`track` is `<lang>/manual`, `<lang>/auto`, or `<lang>/stt`. Locally transcribed files add a
`stt_model:` line and the header reads `captions: en (stt, large-v3-turbo-q5_0)`.

**Text** (`--format txt`): a one-line header, then `[mm:ss] paragraph` blocks separated by blank
lines. Best for reading or pasting.

**JSON** (`--format json`):

```json
{
  "id": "PcpkBzcRdSU",
  "url": "https://www.youtube.com/watch?v=PcpkBzcRdSU",
  "title": "...",
  "channel": "Benjamin Blodgett",
  "duration_s": 325,
  "upload_date": "2022-05-01",
  "track": "en/auto",
  "stt_model": null,
  "words": 1039,
  "paragraphs": [{ "start_s": 0.0, "text": "..." }]
}
```

With several inputs, `md` and `txt` bodies are separated by a `---` line and `json` becomes an
array. `yt2frame --format json` is always an array of `{id, t, path, width, height, cached}`.

## Agent contract

- **stdout** carries only the result: the transcript, or with `--save` one line per video
  `OK <path> words=<n> track=<lang>/<manual|auto|stt> duration=<s> [cached=1]`; for
  `yt2frame`, one line per frame `FRAME <path> t=<seconds> <w>x<h> [cached=1]`.
- **stderr** carries progress and failures: `FAIL <input> <reason>`.
- **Exit codes:** `0` all inputs succeeded, `1` at least one failed, `130` interrupted.
- Missing tools fail fast with the fix in the message, e.g.
  `FAIL <id> whisper-cli not found on PATH (brew install whisper-cpp)`.
- Recommended loop for an agent: `yt2txt URL --save --out <project dir>`, index or read the
  file, pick timestamps where the speaker refers to something visual, then one
  `yt2frame URL t1 t2 t3 --out <dir>` call and read the JPEGs.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `YT_TRANSCRIPT_DIR` | `~/.local/share/yt-transcripts` | Transcript cache; frames go in its `frames/` subfolder |
| `YT2TXT_MODEL` | `large-v3-turbo-q5_0` | Default whisper.cpp model name (`--model` overrides) |
| `YT2TXT_MODEL_DIR` | `~/.cache/yt2txt/models` | Where ggml models are stored |
| `YT_TRANSCRIPT_COOKIES_BROWSER` | unset | Browser whose cookies yt-dlp uses from the start (`chrome`, `firefox`, `safari`) |
| `YT2TXT_FALLBACK_BROWSER` | `chrome` | Browser tried once when YouTube demands sign-in; set empty to disable |

## Models and machine load

Models are whisper.cpp ggml files from
[ggerganov/whisper.cpp on Hugging Face](https://huggingface.co/ggerganov/whisper.cpp), downloaded
on first use. Any name from that repo works with `--model`, without the `ggml-` prefix and `.bin`.

| Model | Size | Notes |
|---|---|---|
| `large-v3-turbo-q5_0` (default) | 574 MB | Near-best accuracy, multilingual, fast on Metal |
| `large-v3-turbo-q8_0` | 874 MB | Slightly higher fidelity than q5 |
| `small-q5_1` | 190 MB | Light and quick; noticeably weaker on Portuguese and jargon |
| `base-q5_1` | 60 MB | Rough; fine for "what is this about", not for quoting |

Default priority is `nice -n 10` with half the CPU cores, one video at a time, so the machine
stays usable. Most of the work runs on the GPU; on an M1 Max `whisper-cli` sits under 10% CPU.

Measured on an M1 Max (10 cores), 5-minute talk, download included:

| Mode | Wall time |
|---|---|
| default (`nice -n 10`, 5 threads) | 18 s |
| `--fast` (10 threads) | 16 s |

Roughly 3 to 4 minutes per hour of audio. Captions take a few seconds. Frames take well under a
second each after a one-time stream lookup.

## Cookies and YouTube's bot check

YouTube sometimes answers with "Sign in to confirm you're not a bot", or a video is members-only
or age-restricted. Both tools retry that step once with cookies from your browser (Chrome by
default, `YT2TXT_FALLBACK_BROWSER` to change or disable). To use cookies from the start, pass
`--cookies-from-browser firefox` (or `chrome`, `safari`) or set `YT_TRANSCRIPT_COOKIES_BROWSER`.
Captions are not Premium-gated, so cookies are a fallback rather than the default; yt-dlp warns
that heavy cookie use can get an account rate-limited.

Keep `yt-dlp` current (`brew upgrade yt-dlp`). Most breakage is an outdated extractor.

## Cache layout

```
~/.local/share/yt-transcripts/
  <id>-<title-slug>.md            transcripts (Markdown, canonical)
  frames/<id>-<hhmmss>.jpg        snapshots
~/.cache/yt2txt/models/
  ggml-<model>.bin                whisper.cpp models
```

Cache hits print `cached=1` on the `OK` / `FRAME` line. `--force` refetches. Delete files freely;
everything is reproducible.

## Claude Code skill

`skill/yt-transcript/SKILL.md` is a Claude Code skill that triggers on pasted YouTube links and
requests like "what does this video say" or "transcribe this". It tells the agent to run
`yt2txt --save --out <project>/.localdev/reference/transcripts`, index the file with
context-mode, answer from search with `[mm:ss]` quotes, and use `yt2frame` for moments that
refer to something on screen. `install.sh` links it into `~/.claude/skills/yt-transcript`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `yt2txt: command not found` | `./install.sh`; make sure `~/.local/bin` is on `PATH` |
| `whisper-cli not found on PATH` | `brew install whisper-cpp` |
| `yt-dlp exit 1: ... Sign in to confirm ...` after the cookie retry | Log in to YouTube in Chrome, or pass `--cookies-from-browser <your browser>` |
| `yt-dlp exit 1: This video is unavailable` | Private or removed video, or a bad id |
| `no frame at Ns (past the end of the video?)` | The timestamp exceeds the duration |
| Black frame | You hit a fade or cut; try a second earlier or later |
| Wrong caption language | `--langs <lang> --force`; for local transcription `--language <xx>` |
| Poor auto captions | `--stt --force` to transcribe locally instead |
| Slow local transcription | `--fast`, or `--model small-q5_1` for a lighter model |
| Model download interrupted | Just re-run; a partial `.part` file is discarded and restarted |

## Development

```sh
make test          # uv sync + pytest (51 tests, no network, no whisper-cli needed)
make lint          # ruff check + format check
make install       # same as ./install.sh
```

Layout:

```
src/yt2txt/
  cli.py          yt2txt: argument parsing, cache, cookie retry, output
  frame_cli.py    yt2frame: argument parsing and FRAME output
  youtube.py      yt-dlp wrappers: metadata, caption tracks, json3 parsing, audio download
  stt.py          whisper-cli: model download, command line, JSON parsing
  frames.py       stream URL resolution, ffmpeg single-frame grab, timestamp parsing
  render.py       Transcript model, Markdown/text/JSON renderers, cached-Markdown parser
skill/yt-transcript/SKILL.md
tests/            pytest with fixtures for json3 and whisper-cli JSON
install.sh        brew deps, uv tool install, skill symlink
```

Adding another speech-to-text backend means implementing
`transcribe(wav, model, language, fast, tmp, log) -> (cues, language)` next to the whisper.cpp
one in `stt.py`; everything downstream only sees cues.

## Limitations and non-goals

- Captions, audio and frames come from YouTube via yt-dlp; when YouTube changes something,
  upgrading yt-dlp is the fix.
- Local transcription is macOS/Apple Silicon first. whisper.cpp also builds on Linux, but that
  path is untested here.
- No playlists, no speaker diarization, no word-level timestamps, no time ranges or
  every-N-seconds sampling for frames. All are possible additions; none are planned.
- Transcripts and frames are other people's content. Keep project copies out of version control
  unless you have decided otherwise.

## License

MIT, see [LICENSE](LICENSE).
