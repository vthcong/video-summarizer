import re
from pathlib import Path

from .models import Result

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"


def _path(video_id: str, language: str, model: str, effort: str) -> Path:
    safe_lang = re.sub(r"[^A-Za-z0-9_-]", "_", language)
    return CACHE_DIR / f"{video_id}.{safe_lang}.{model}.{effort}.json"


def load(video_id: str, language: str, model: str, effort: str) -> Result | None:
    path = _path(video_id, language, model, effort)
    if not path.exists():
        return None
    try:
        return Result.model_validate_json(path.read_text())
    except ValueError:
        return None  # stale or corrupt entry; regenerate


def save(result: Result, model: str) -> None:
    """`model` is the alias that was requested ("opus"), so later lookups by alias find it."""
    CACHE_DIR.mkdir(exist_ok=True)
    path = _path(result.video.id, result.language, model, result.effort)
    path.write_text(result.model_dump_json(indent=2))
