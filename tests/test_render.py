import json

from yt2txt import render


def test_blocks_split_on_time_and_chapter():
    cues = [(0, "a"), (30, "b"), (65, "c"), (70, "d"), (200, "e")]
    out = render.blocks(cues, 60, [{"start_time": 68}])
    assert out == [(0, "a b"), (65, "c"), (70, "d"), (200, "e")]


def test_stamp():
    assert render.stamp(5) == "00:05"
    assert render.stamp(3725) == "1:02:05"


def test_render_md_caption_track_matches_legacy_layout(meta):
    t = render.build(meta, [(1.0, "hello world"), (65.0, "second")], "en", "manual", 60)
    md = render.render_md(t)
    assert "track: en/manual\n" in md and "stt_model" not in md
    assert 'title: "A Test: Video!"' in md
    assert "captions: en (manual)" in md
    assert "## Chapters" in md and "- [01:08] Part 2" in md
    assert "**[00:01]** hello world" in md and "**[01:05]** second" in md


def test_render_md_stt_track_adds_model(meta):
    t = render.build(meta, [(0.0, "x")], "pt", "stt", 60, stt_model="large-v3-turbo-q5_0")
    md = render.render_md(t)
    assert "track: pt/stt\nstt_model: large-v3-turbo-q5_0\n" in md
    assert "captions: pt (stt, large-v3-turbo-q5_0)" in md


def test_parse_md_roundtrip(meta):
    t = render.build(meta, [(1.0, "hello world"), (3725.0, "late")], "en", "auto", 60)
    back = render.parse_md(render.render_md(t))
    assert (back.id, back.title, back.channel, back.duration_s, back.track) == (
        t.id,
        t.title,
        t.channel,
        t.duration_s,
        t.track,
    )
    assert back.paragraphs == [(1.0, "hello world"), (3725.0, "late")]
    assert back.words == t.words


def test_render_json_and_txt(meta):
    t = render.build(meta, [(1.0, "hello world")], "en", "auto", 60)
    d = json.loads(render.render_json(t))
    assert d["id"] == meta["id"] and d["paragraphs"] == [{"start_s": 1.0, "text": "hello world"}]
    assert d["words"] == 2 and d["track"] == "en/auto"
    txt = render.render_txt(t)
    assert txt.startswith("A Test: Video! — Chan — https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "[00:01] hello world" in txt


def test_slug():
    assert render.slug("A Test: Video!") == "a-test-video"
    assert render.slug("!!!") == "video"
