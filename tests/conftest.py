from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

META = {
    "id": "dQw4w9WgXcQ",
    "title": "A Test: Video!",
    "channel": "Chan",
    "duration": 3725,
    "upload_date": "20240102",
    "description": "line one\nline two",
    "chapters": [{"start_time": 0, "title": "Intro"}, {"start_time": 68, "title": "Part 2"}],
}


@pytest.fixture
def meta():
    return dict(META)


@pytest.fixture
def fixtures():
    return FIXTURES
