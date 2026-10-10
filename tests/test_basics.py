import pytest

from app import summarizer
from app.models import Segment
from app.summarizer import format_timestamp, format_transcript
from app.youtube import parse_video_id

VID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        VID,
        f"https://www.youtube.com/watch?v={VID}",
        f"https://youtube.com/watch?v={VID}&t=42s&list=PL123",
        f"https://m.youtube.com/watch?feature=share&v={VID}",
        f"youtube.com/watch?v={VID}",
        f"https://youtu.be/{VID}",
        f"https://youtu.be/{VID}?si=abc123",
        f"https://www.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/embed/{VID}",
        f"https://www.youtube.com/live/{VID}?feature=share",
        f"https://www.youtube-nocookie.com/embed/{VID}",
        f"  https://youtu.be/{VID}  ",
    ],
)
def test_parse_video_id_valid(url):
    assert parse_video_id(url) == VID


@pytest.mark.parametrize(
    "url",
    [
        "",
        "hello world",
        "https://vimeo.com/123456",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/@somechannel",
        "https://evil.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_parse_video_id_invalid(url):
    assert parse_video_id(url) is None


def test_format_timestamp():
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(75.9) == "01:15"
    assert format_timestamp(3725) == "1:02:05"


def test_format_transcript_merges_into_blocks():
    segments = [Segment(start=t, text=f"s{t}") for t in (0, 10, 20, 31, 45, 70)]
    assert format_transcript(segments) == "[00:00] s0 s10 s20\n[00:31] s31 s45\n[01:10] s70"


def test_backend_prefers_claude_code_then_codex(monkeypatch):
    monkeypatch.delenv("SUMMARIZER_BACKEND", raising=False)
    monkeypatch.delenv("CLAUDE_BIN", raising=False)
    monkeypatch.delenv("CODEX_BIN", raising=False)
    installed = set()
    monkeypatch.setattr(summarizer.shutil, "which", lambda name: name if name in installed else None)

    assert summarizer.get_backend() == "claude-code"  # nothing installed: report Claude Code missing
    installed.add("codex")
    assert summarizer.get_backend() == "codex"
    installed.add("claude")
    assert summarizer.get_backend() == "claude-code"
    monkeypatch.setenv("SUMMARIZER_BACKEND", "codex")
    assert summarizer.get_backend() == "codex"


def test_cache_model_key(monkeypatch):
    monkeypatch.setenv("SUMMARIZER_BACKEND", "claude-code")
    assert summarizer.cache_model_key("opus") == "opus"
    monkeypatch.setenv("SUMMARIZER_BACKEND", "codex")
    monkeypatch.delenv("CODEX_MODEL", raising=False)
    assert summarizer.cache_model_key("opus") == "codex-default"
    monkeypatch.setenv("CODEX_MODEL", "gpt-5.5")
    assert summarizer.cache_model_key("opus") == "codex-gpt-5_5"
