"""yt2txt: YouTube URL in, transcript out."""

__version__ = "0.2.0"


class Yt2TxtError(Exception):
    """A per-video failure with a message suitable for a FAIL line."""
