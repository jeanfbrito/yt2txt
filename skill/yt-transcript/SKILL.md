---
name: yt-transcript
description: Turns a YouTube video into a transcript (YouTube captions when they exist, otherwise local whisper.cpp speech-to-text, no API key) as timestamped Markdown via the `yt2txt` CLI, caches it, indexes it into context-mode so ctx_search can answer from it, and optionally files the durable lessons. Use whenever the user pastes a youtube.com or youtu.be link, or says "watch this video", "what does this video say", "get the transcript", "transcribe this video", "summarize this talk", "use this video as a source", "add this video as reference". Also for batches of links in a references list.
---

# YouTube transcript → searchable knowledge

Turn a YouTube link into a source you can actually read and cite: run `yt2txt`, which
fetches the captions with `yt-dlp` or, when the video has none, downloads the audio and
transcribes it locally with whisper.cpp. Either way you get a clean timestamped Markdown
file; search it and answer from the text with timestamps. The raw transcript does not have
to enter the main context.

Works the same from Claude Code, Codex and Grok Build: everything below is shell commands
plus your host's file-reading and image-viewing tools. Where a step names an optional tool
(a search index, a memory store, background subagents), use your host's equivalent or skip it.

## When to use

- The user pastes a YouTube URL and asks anything about it.
- A references list contains video links (tutorials, devlogs, GDC talks).
- You want to cite a video with a timestamp instead of from memory.

Videos without captions work too; they just take longer (local transcription). Tell the
user when that path is taken so the wait is expected.

## Procedure

1. **Fetch.** Run the CLI (seconds per video with captions; minutes without):

   ```bash
   yt2txt <url> [<url> ...] --save --out <project>/.localdev/reference/transcripts
   ```

   - `--save` writes to the global cache `~/.local/share/yt-transcripts/<id>-<slug>.md`
     (override with `YT_TRANSCRIPT_DIR`). `--out` adds a copy next to the project so
     project-scoped indexing and handoffs can point at it. Skip `--out` outside a
     project or when `.localdev/` does not exist.
   - Track choice: manual subtitles first, then auto captions, in `--langs` order
     (default `en,en-orig,pt,pt-BR,pt-PT`). `en-orig` is YouTube's untranslated auto
     track and is usually the cleanest. No track at all → local whisper.cpp
     (`track=xx/stt` in the OK line, `xx` = detected language).
   - Local transcription runs at low priority (nice, half the cores) so the machine
     stays usable. Add `--fast` when the user is not doing anything else. Add `--stt`
     to force local transcription when auto captions are unusable.
   - Cached videos are reused; pass `--force` to refetch.
   - Output line per video: `OK <path> words=N track=en/auto duration=S`. Anything
     else is a failure to report verbatim.
   - Several links: pass them all to one `yt2txt` call. If your host offers cheap
     background subagents, one of them can run the command and return the OK lines.
   - Need the text in context instead of a file? `yt2txt <url> --format txt` (or
     `json`) prints it to stdout; only do this for short videos.

   - **See what was on screen.** When the transcript mentions something visual ("as you
     can see here", a slide, a demo, a diagram), grab frames at those stamps without
     downloading the video with the sister command: `yt2frame <url> 2:30 4:10 --out <dir>`
     prints `FRAME <path> t=150 1280x720` per frame in well under a second each; then open
     the JPEGs with your host's image-viewing / file-reading tool. Batch every timestamp
     you need into one call. A black frame means a fade or
     cut at that instant; nudge the time by a second or two.

2. **Make it searchable.** If a search index is available (for example context-mode's
   `ctx_index` / `ctx_search`), index each written file or the `--out` directory, preferring
   the project copy so the knowledge is project-scoped. Without one, `grep -n` the
   Markdown for the user's terms, or read `yt2txt <url> --format txt` when the video is
   short.

3. **Answer from the transcript, not from memory.** Search with the user's question plus
   3–5 sub-questions; quote with the `[mm:ss]` stamps the file carries. Read the file in
   full only when the user asks for a full summary and it is short (under ~3,000 words),
   otherwise summarize from the passages you found.

4. **Record what is durable (optional).** When the video changes how the project
   should work (a technique, a parameter, a pitfall), add it where the project keeps
   references (`docs/references/…`, a skill's `references/sources.md`) with the URL,
   title, channel, and a two-line takeaway. Write to a persistent memory store (if your
   host has one) only when the user asks to remember it.

## File format

Frontmatter (`source`, `id`, `url`, `title`, `channel`, `duration_s`,
`upload_date`, `fetched`, `track`, `stt_model` when transcribed locally, `words`),
then `# Title`, an optional `## Description` (first 40 lines) and `## Chapters`, then
`## Transcript` as paragraphs of about 60 s each, prefixed `**[mm:ss]**`. Paragraphs
also break at chapter boundaries. Auto captions have no punctuation; whisper.cpp
output does. Do not "fix" the file, quote it as is and paraphrase in your answer.

## Failure handling

- `yt2txt not found` / `yt2frame not found`: run `~/Github/yt2txt/install.sh` (installs the
  CLIs with uv, the brew deps, and links this skill).
- `whisper-cli not found on PATH`: `brew install whisper-cpp`. The first local
  transcription also downloads a 574 MB model into `~/.cache/yt2txt/models/`.
- `yt-dlp exit N`: paste the stderr tail; common causes are a private/age-gated
  video or an outdated `yt-dlp` (`brew upgrade yt-dlp`).
- `Sign in to confirm you're not a bot` or members-only / age-gated: `yt2txt` already
  retries once with Chrome cookies (`YT2TXT_FALLBACK_BROWSER`). If it still fails, rerun
  with `--cookies-from-browser firefox` (or `safari`), or export
  `YT_TRANSCRIPT_COOKIES_BROWSER=chrome` to use cookies from the start. This reuses the user's logged-in YouTube
  session (a Premium account works the same way). Captions themselves are not
  Premium-gated, so cookies are a fallback, not the default; yt-dlp warns that heavy
  cookie use can get an account rate-limited, so use it only when the plain run fails.
- Wrong language picked: rerun with `--langs <lang>` and `--force`; for local
  transcription use `--language <xx>`.
- A very long video with no captions: warn the user about the wait (roughly a few
  minutes per hour of audio at default priority) before running, or pass `--fast`.

## Notes

- Requirements: `yt2txt` and `yt2frame` on PATH (one uv tool install), `yt-dlp`, `ffmpeg`, `whisper-cpp`.
  No API key; audio and text never leave the machine.
- Transcripts are other people's content: keep the project copy under
  `.localdev/` (uncommitted) unless the user decides otherwise.
- `yt2txt --help` and `yt2frame --help` list every flag. This skill lives in the tool's own
  repo (`~/Github/yt2txt/skill/yt-transcript`); the README there documents the CLIs.
- Host notes: `install.sh` links this folder into `~/.claude/skills`, `~/.codex/skills` and
  `~/.grok/skills` when those hosts are present. Grok Build also scans `~/.claude/skills`
  on its own; Codex and Grok both read a project's `AGENTS.md`, so a one-line pointer
  there ("YouTube links: use the yt-transcript skill / `yt2txt`") helps discovery.
