import logging
import os
import signal
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from . import cache  # noqa: E402
from .models import Effort, Job, ModelChoice, Result  # noqa: E402
from .summarizer import SummaryError, summarize  # noqa: E402
from .transcript import get_transcript  # noqa: E402
from .youtube import VideoUnavailableError, fetch_metadata, parse_video_id  # noqa: E402

log = logging.getLogger("uvicorn.error")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Set by the Chrome launcher so an on-demand server doesn't run forever. 0 = never stop.
IDLE_SHUTDOWN_MINUTES = float(os.getenv("IDLE_SHUTDOWN_MINUTES", "0"))

jobs: dict[str, Job] = {}
last_activity = time.monotonic()


def _idle_watchdog() -> None:
    idle_limit = IDLE_SHUTDOWN_MINUTES * 60
    while True:
        time.sleep(min(30, idle_limit / 2))
        busy = any(job.status not in ("done", "error") for job in jobs.values())
        if not busy and time.monotonic() - last_activity > idle_limit:
            log.info("No activity for %g minutes; shutting down.", IDLE_SHUTDOWN_MINUTES)
            os.kill(os.getpid(), signal.SIGTERM)  # uvicorn handles this as a graceful shutdown
            return


@asynccontextmanager
async def lifespan(app: FastAPI):
    if IDLE_SHUTDOWN_MINUTES > 0:
        threading.Thread(target=_idle_watchdog, daemon=True).start()
    yield


app = FastAPI(title="YouTube Video Summarizer", lifespan=lifespan)


@app.middleware("http")
async def track_activity(request: Request, call_next):
    global last_activity
    last_activity = time.monotonic()
    return await call_next(request)


class SummarizeRequest(BaseModel):
    url: str
    language: str = "English"
    model: ModelChoice = "sonnet"
    effort: Effort = "high"


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    # The Chrome launcher checks this to tell our server apart from anything else on the port.
    return {"app": "video-summarizer"}


@app.post("/api/summarize")
def start_summary(req: SummarizeRequest, background: BackgroundTasks) -> Job:
    video_id = parse_video_id(req.url)
    if video_id is None:
        raise HTTPException(400, "That doesn't look like a YouTube video URL.")
    language = req.language.strip() or "English"

    job = Job(id=uuid.uuid4().hex)
    if cached := cache.load(video_id, language, req.model, req.effort):
        job.status, job.result = "done", cached
    else:
        background.add_task(_run_job, job, video_id, language, req.model, req.effort)
    jobs[job.id] = job
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> Job:
    if job_id not in jobs:
        raise HTTPException(404, "Job not found.")
    return jobs[job_id]


def _run_job(job: Job, video_id: str, language: str, model: ModelChoice, effort: Effort) -> None:
    def set_status(status: str) -> None:
        job.status = status

    try:
        video = fetch_metadata(video_id)
        segments, source = get_transcript(video_id, on_status=set_status)
        set_status("summarizing")
        summary, model_id = summarize(segments, video, language, model, effort)
        result = Result(
            video=video, summary=summary, transcript_source=source,
            language=language, model=model_id, effort=effort,
        )
        cache.save(result, model)
        job.result = result
        job.status = "done"
    except (VideoUnavailableError, SummaryError) as e:
        job.error, job.status = str(e), "error"
    except Exception:
        log.exception("Job %s failed", job.id)
        job.error, job.status = "Something went wrong. Check the server logs for details.", "error"
