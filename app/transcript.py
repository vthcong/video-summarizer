import os
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import yt_dlp
from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    InvalidVideoId,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

from .models import Segment
from .youtube import VideoUnavailableError, _clean_ytdlp_error

TranscriptSource = Literal["captions", "whisper"]
StatusCallback = Callable[[str], None]

_whisper_model = None
_whisper_lock = threading.Lock()


def get_transcript(
    video_id: str, on_status: StatusCallback = lambda s: None
) -> tuple[list[Segment], TranscriptSource]:
    """Captions if YouTube has them, otherwise download the audio and transcribe it locally."""
    on_status("fetching_transcript")
    try:
        return _fetch_captions(video_id), "captions"
    except (VideoUnavailable, InvalidVideoId) as e:
        raise VideoUnavailableError("This video is unavailable.") from e
    except CouldNotRetrieveTranscript:
        # Captions disabled, none found, or YouTube blocked the request - try the audio instead.
        pass

    with tempfile.TemporaryDirectory(prefix="yt-audio-") as tmp:
        on_status("downloading_audio")
        audio_path = _download_audio(video_id, Path(tmp))
        on_status("transcribing")
        return _transcribe(audio_path), "whisper"


def _fetch_captions(video_id: str) -> list[Segment]:
    transcripts = list(YouTubeTranscriptApi().list(video_id))
    if not transcripts:
        raise CouldNotRetrieveTranscript(video_id)

    # Prefer human-written captions over auto-generated ones, and English among equals.
    # The summary language is handled by Claude, so any caption language works.
    transcripts.sort(key=lambda t: (t.is_generated, not t.language_code.startswith("en")))
    fetched = transcripts[0].fetch()
    return [Segment(start=s.start, text=s.text) for s in fetched if s.text.strip()]


def _download_audio(video_id: str, out_dir: Path) -> Path:
    # No post-processing, so no ffmpeg binary is needed: faster-whisper decodes m4a/webm itself.
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            return Path(ydl.prepare_filename(info))
    except yt_dlp.utils.DownloadError as e:
        raise VideoUnavailableError(_clean_ytdlp_error(e)) from e


def _get_whisper_model():
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is None:
            from faster_whisper import WhisperModel

            size = os.getenv("WHISPER_MODEL", "small")
            _whisper_model = WhisperModel(size, device="cpu", compute_type="int8")
        return _whisper_model


def _transcribe(audio_path: Path) -> list[Segment]:
    model = _get_whisper_model()
    segments, _info = model.transcribe(str(audio_path), vad_filter=True)
    # `segments` is a lazy generator - transcription happens while iterating.
    return [Segment(start=s.start, text=s.text.strip()) for s in segments if s.text.strip()]
