import json
import subprocess
import sys

import pytest

from yt2txt import cli, render


@pytest.fixture
def cache(tmp_path, monkeypatch, meta):
    monkeypatch.setattr(cli, "CACHE_DIR", tmp_path)
    t = render.build(meta, [(1.0, "hello world"), (65.0, "second")], "en", "manual", 60)
    (tmp_path / f"{meta['id']}-{render.slug(meta['title'])}.md").write_text(render.render_md(t))
    return tmp_path


def run(argv, capsys):
    rc = cli.main(argv)
    out = capsys.readouterr()
    return rc, out.out, out.err


def test_cached_md_is_emitted_verbatim(cache, capsys, meta):
    rc, out, err = run([meta["id"]], capsys)
    assert rc == 0
    assert out == next(cache.glob("*.md")).read_text()


def test_cached_json_shape(cache, capsys, meta):
    rc, out, _ = run([meta["id"], "--format", "json"], capsys)
    d = json.loads(out)
    assert d["track"] == "en/manual" and len(d["paragraphs"]) == 2


def test_cached_txt(cache, capsys, meta):
    rc, out, _ = run([meta["id"], "--format", "txt"], capsys)
    assert "[01:05] second" in out


def test_save_prints_ok_line_and_copies(cache, capsys, meta, tmp_path):
    out_dir = tmp_path / "proj"
    rc, out, _ = run([meta["id"], "--out", str(out_dir)], capsys)
    assert rc == 0
    assert out.startswith(f"OK {out_dir}/") and "track=en/manual" in out and "cached=1" in out
    assert list(out_dir.glob("*.md"))


def test_multiple_json_is_array(cache, capsys, meta):
    rc, out, _ = run([meta["id"], meta["id"], "--format", "json"], capsys)
    assert isinstance(json.loads(out), list)


def test_bad_id_fails_with_exit_1(cache, capsys):
    rc, out, err = run(["not a video"], capsys)
    assert rc == 1 and out == "" and err.startswith("FAIL not a video")


def test_missing_ytdlp_named(cache, capsys, monkeypatch):
    monkeypatch.setenv("PATH", "")
    rc, out, err = run(["aaaaaaaaaaa"], capsys)
    assert rc == 1 and "yt-dlp not found" in err and "brew install yt-dlp" in err


def test_help_runs():
    r = subprocess.run([sys.executable, "-m", "yt2txt.cli", "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "--stt" in r.stdout


def test_is_bot_check():
    assert cli.is_bot_check("ERROR: [youtube] x: Sign in to confirm you\u2019re not a bot.")
    assert cli.is_bot_check("This video is age-restricted")
    assert not cli.is_bot_check("This video is unavailable")


def test_bot_check_retries_with_browser_cookies(cache, capsys, monkeypatch, meta):
    calls = []

    def fake_fetch(vid, a, extra, log):
        calls.append(list(extra))
        if "--cookies-from-browser" not in extra:
            raise cli.Yt2TxtError("yt-dlp exit 1: Sign in to confirm you're not a bot")
        return render.build(meta, [(0.0, "ok")], "en", "auto", 60)

    monkeypatch.setattr(cli, "fetch", fake_fetch)
    monkeypatch.delenv("YT_TRANSCRIPT_COOKIES_BROWSER", raising=False)
    monkeypatch.setenv("YT2TXT_FALLBACK_BROWSER", "firefox")
    rc, out, err = run(["aaaaaaaaaaa", "--format", "txt", "--force"], capsys)
    assert rc == 0 and "[00:00] ok" in out
    assert calls == [[], ["--cookies-from-browser", "firefox"]]
    assert "retrying with firefox cookies" in err


def test_fallback_disabled_by_empty_env(cache, capsys, monkeypatch):
    def fake_fetch(vid, a, extra, log):
        raise cli.Yt2TxtError("Sign in to confirm you're not a bot")

    monkeypatch.setattr(cli, "fetch", fake_fetch)
    monkeypatch.delenv("YT_TRANSCRIPT_COOKIES_BROWSER", raising=False)
    monkeypatch.setenv("YT2TXT_FALLBACK_BROWSER", "")
    rc, out, err = run(["aaaaaaaaaaa", "--force"], capsys)
    assert rc == 1 and "FAIL" in err and "retrying" not in err
