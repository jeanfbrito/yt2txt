.PHONY: install test lint uninstall

install:
	./install.sh

test:
	uv sync --group dev --quiet
	uv run pytest -q

lint:
	uvx ruff check src tests
	uvx ruff format --check src tests

uninstall:
	-uv tool uninstall yt2txt
	-rm -f $${CLAUDE_SKILLS_DIR:-$$HOME/.claude/skills}/yt-transcript $$HOME/.codex/skills/yt-transcript $$HOME/.grok/skills/yt-transcript
