from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Segment(BaseModel):
    start: float  # seconds from the start of the video
    text: str


class Chapter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_seconds: int = Field(description="Start of the chapter, taken from a transcript timestamp")
    title: str
    summary: str = Field(description="One or two sentences on what this part covers")


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tldr: str = Field(description="Two or three sentences capturing the whole video")
    key_points: list[str] = Field(description="The most important takeaways, one per item")
    chapters: list[Chapter] = Field(description="Chronological sections of the video")


class VideoInfo(BaseModel):
    id: str
    title: str
    channel: str | None = None
    duration: int | None = None  # seconds
    thumbnail: str | None = None


# Claude Code model aliases; each resolves to the latest model of that family.
ModelChoice = Literal["opus", "sonnet", "haiku"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Result(BaseModel):
    video: VideoInfo
    summary: Summary
    transcript_source: Literal["captions", "whisper"]
    language: str
    model: str  # the exact model that wrote the summary, e.g. "claude-opus-5-5"
    effort: Effort


JobStatus = Literal[
    "queued",
    "fetching_transcript",
    "downloading_audio",
    "transcribing",
    "summarizing",
    "done",
    "error",
]


class Job(BaseModel):
    id: str
    status: JobStatus = "queued"
    error: str | None = None
    result: Result | None = None
