#!/usr/bin/env bash
# Install yt2txt + yt2frame and link the Claude Code skill. Safe to re-run.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SRC="$HERE/skill/yt-transcript"
SKILL_DST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}/yt-transcript"

need() { command -v "$1" >/dev/null 2>&1; }

if ! need brew; then echo "Homebrew is required (https://brew.sh)"; exit 1; fi
if ! need uv; then echo "uv is required: brew install uv"; exit 1; fi

missing=()
need yt-dlp      || missing+=(yt-dlp)
need ffmpeg      || missing+=(ffmpeg)
need whisper-cli || missing+=(whisper-cpp)
if ((${#missing[@]})); then
  echo "installing with brew: ${missing[*]}"
  brew install "${missing[@]}"
fi

echo "installing yt2txt + yt2frame with uv"
uv tool install "$HERE" --force --reinstall --quiet

mkdir -p "$(dirname "$SKILL_DST")"
if [ -L "$SKILL_DST" ] || [ -e "$SKILL_DST" ]; then rm -rf "$SKILL_DST"; fi
ln -s "$SKILL_SRC" "$SKILL_DST"

echo
echo "ok  $(command -v yt2txt)   ($(yt2txt --version))"
echo "ok  $(command -v yt2frame)"
echo "ok  skill: $SKILL_DST -> $SKILL_SRC"
echo
echo "try: yt2txt https://youtu.be/jNQXAC9IVRw --format txt"
