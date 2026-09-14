import pytest

from yt2txt import Yt2TxtError
from yt2txt.youtube import parse_json3, pick_track, video_id


@pytest.mark.parametrize(
    "s",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ?feature=share",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "dQw4w9WgXcQ",
        "  dQw4w9WgXcQ\n",
    ],
)
def test_video_id(s):
    assert video_id(s) == "dQw4w9WgXcQ"


def test_video_id_rejects_garbage():
    with pytest.raises(Yt2TxtError):
        video_id("https://example.com/nothing")


def test_pick_track_prefers_manual_in_lang_order():
    meta = {"subtitles": {"pt": []}, "automatic_captions": {"en": [], "pt": []}}
    assert pick_track(meta, ["en", "pt"]) == ("pt", "manual")
    assert pick_track({"automatic_captions": {"en-orig": []}}, ["en", "en-orig"]) == ("en-orig", "auto")
    assert pick_track({"subtitles": {"de": []}}, ["en"]) == ("de", "manual")
    assert pick_track({}, ["en"]) == (None, None)


def test_parse_json3_skips_music_and_appends(fixtures):
    cues = parse_json3(fixtures / "sample.json3")
    assert cues == [(1.0, "hello world"), (65.0, "second paragraph"), (70.0, "after chapter")]
