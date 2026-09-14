from pathlib import Path

from yt2txt import stt


def test_parse_whisper_json(fixtures):
    cues, lang = stt.parse_whisper_json(fixtures / "whisper.json")
    assert lang == "pt"
    assert cues == [(0.0, "Olá pessoal,"), (3.5, "tudo bem?"), (72.0, "Segundo bloco.")]


def test_build_cmd_nice_and_threads():
    cmd = stt.build_cmd(
        "/bin/whisper-cli", Path("m.bin"), Path("a.wav"), Path("/tmp/out"), None, threads=5, nice=True
    )
    assert cmd[:3] == ["nice", "-n", str(stt.NICE_LEVEL)]
    assert "-l" in cmd and cmd[cmd.index("-l") + 1] == "auto"
    assert cmd[cmd.index("-t") + 1] == "5"
    assert "-oj" in cmd and "-np" in cmd and cmd[cmd.index("-of") + 1] == "/tmp/out"


def test_build_cmd_fast_has_no_nice():
    cmd = stt.build_cmd("w", Path("m"), Path("a"), Path("o"), "pt", threads=10, nice=False)
    assert cmd[0] == "w" and cmd[cmd.index("-l") + 1] == "pt"


def test_default_threads(monkeypatch):
    monkeypatch.setattr(stt.os, "cpu_count", lambda: 10)
    assert stt.default_threads(fast=False) == 5
    assert stt.default_threads(fast=True) == 10
