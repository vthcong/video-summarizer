import re
from urllib.parse import parse_qs, urlparse

import yt_dlp

from .models import VideoInfo

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}


def parse_video_id(url: str) -> str | None:
    """Return the 11-character video ID from any common YouTube URL form, or None."""
    url = url.strip()
    if _ID_RE.match(url):
        return url
    if "://" not in url:
        url = "https://" + url

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    candidate = None
    if host in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host in _YOUTUBE_HOSTS or host == "www.youtube-nocookie.com":
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [None])[0]
        else:
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live", "v"}:
                candidate = parts[1]

    if candidate and _ID_RE.match(candidate):
        return candidate
    return None


class VideoUnavailableError(Exception):
    pass


def fetch_metadata(video_id: str) -> VideoInfo:
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    except yt_dlp.utils.DownloadError as e:
        raise VideoUnavailableError(_clean_ytdlp_error(e)) from e

    return VideoInfo(
        id=video_id,
        title=info.get("title") or video_id,
        channel=info.get("channel") or info.get("uploader"),
        duration=info.get("duration"),
        thumbnail=info.get("thumbnail"),
    )


def _clean_ytdlp_error(e: Exception) -> str:
    msg = str(e)
    # yt-dlp prefixes messages with "ERROR: [youtube] <id>: "
    return re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*[\w-]+:\s*)?", "", msg).strip() or "Video is unavailable."
