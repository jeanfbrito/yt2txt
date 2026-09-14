import json

import pytest

from yt2txt import frame_cli


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.setattr(frame_cli.frames, "stream_url", lambda url, extra, h: "http://stream")

    def fake_grab(stream, t, out):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"jpg")
        return out

    monkeypatch.setattr(frame_cli.frames, "grab_frame", fake_grab)
    monkeypatch.setattr(frame_cli.frames, "dimensions", lambda p: (1280, 720))
    monkeypatch.delenv("YT_TRANSCRIPT_COOKIES_BROWSER", raising=False)


def run(argv, capsys):
    rc = frame_cli.main(argv)
    out = capsys.readouterr()
    return rc, out.out, out.err


def test_frame_lines_and_cache(fakes, capsys, tmp_path):
    out_dir = tmp_path / "frames"
    rc, out, err = run(["aaaaaaaaaaa", "2:30", "10", "--out", str(out_dir)], capsys)
    assert rc == 0
    lines = out.strip().splitlines()
    assert lines[0] == f"FRAME {out_dir}/aaaaaaaaaaa-000230.jpg t=150 1280x720"
    assert lines[1] == f"FRAME {out_dir}/aaaaaaaaaaa-000010.jpg t=10 1280x720"
    rc, out, _ = run(["aaaaaaaaaaa", "2:30", "--out", str(out_dir)], capsys)
    assert out.strip().endswith("cached=1")


def test_json_is_array(fakes, capsys, tmp_path):
    rc, out, _ = run(["aaaaaaaaaaa", "5", "--format", "json", "--out", str(tmp_path)], capsys)
    d = json.loads(out)
    assert isinstance(d, list) and d[0]["t"] == 5.0 and d[0]["width"] == 1280


def test_bad_timestamp_fails(fakes, capsys, tmp_path):
    rc, out, err = run(["aaaaaaaaaaa", "nope", "--out", str(tmp_path)], capsys)
    assert rc == 1 and out == "" and "bad timestamp" in err


def test_bot_check_retries_with_cookies(fakes, capsys, monkeypatch, tmp_path):
    calls = []

    def flaky_stream(url, extra, h):
        calls.append(list(extra))
        if "--cookies-from-browser" not in extra:
            raise frame_cli.Yt2TxtError("Sign in to confirm you're not a bot")
        return "http://stream"

    monkeypatch.setattr(frame_cli.frames, "stream_url", flaky_stream)
    monkeypatch.setenv("YT2TXT_FALLBACK_BROWSER", "firefox")
    rc, out, err = run(["aaaaaaaaaaa", "1", "--out", str(tmp_path)], capsys)
    assert rc == 0 and calls == [[], ["--cookies-from-browser", "firefox"]]
