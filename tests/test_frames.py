from pathlib import Path

import pytest

from yt2txt import Yt2TxtError, frames


@pytest.mark.parametrize(
    "s,expected",
    [
        ("90", 90.0),
        ("90.5", 90.5),
        ("2:30", 150.0),
        ("02:05", 125.0),
        ("1:02:03", 3723.0),
        ("0:00", 0.0),
        (" 1:00:00 ", 3600.0),
    ],
)
def test_parse_timestamp(s, expected):
    assert frames.parse_timestamp(s) == expected


@pytest.mark.parametrize("s", ["abc", "1:2:3:4", "", "-5", "2m30s"])
def test_parse_timestamp_rejects(s):
    with pytest.raises(Yt2TxtError):
        frames.parse_timestamp(s)


def test_frame_name():
    assert frames.frame_name("dQw4w9WgXcQ", 150) == "dQw4w9WgXcQ-000230.jpg"
    assert frames.frame_name("dQw4w9WgXcQ", 3723.9) == "dQw4w9WgXcQ-010203.jpg"


def test_ffmpeg_cmd_seeks_before_input():
    cmd = frames.ffmpeg_cmd("http://x/stream", 150, Path("/tmp/o.jpg"))
    assert cmd.index("-ss") < cmd.index("-i") and cmd[cmd.index("-ss") + 1] == "150.000"
    assert cmd[cmd.index("-frames:v") + 1] == "1" and cmd[-1] == "/tmp/o.jpg"
