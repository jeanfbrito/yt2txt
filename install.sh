#!/usr/bin/env bash
# Install yt2txt + yt2frame and link the agent skill into Claude Code, Codex and Grok Build. Safe to re-run.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SRC="$HERE/skill/yt-transcript"
# Skill hosts: Claude Code always; Codex and Grok Build when their config dir exists.
SKILL_DIRS=("${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}")
[ -d "$HOME/.codex" ] && SKILL_DIRS+=("$HOME/.codex/skills")
[ -d "$HOME/.grok" ]  && SKILL_DIRS+=("$HOME/.grok/skills")

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

echo
echo "ok  $(command -v yt2txt)   ($(yt2txt --version))"
echo "ok  $(command -v yt2frame)"
for dir in "${SKILL_DIRS[@]}"; do
  dst="$dir/yt-transcript"
  mkdir -p "$dir"
  if [ -L "$dst" ] || [ -e "$dst" ]; then rm -rf "$dst"; fi
  ln -s "$SKILL_SRC" "$dst"
  echo "ok  skill: $dst -> $SKILL_SRC"
done
echo
echo "try: yt2txt https://youtu.be/jNQXAC9IVRw --format txt"
