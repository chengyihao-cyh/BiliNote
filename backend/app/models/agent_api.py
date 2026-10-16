from typing import Literal

from app.enmus.note_enums import DownloadQuality
from app.enmus.task_status_enums import TaskStatus
from app.validators.video_url_validator import detect_video_platform
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateVideoNoteRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    video_url: str = Field(min_length=1, max_length=2048)
    quality: DownloadQuality = DownloadQuality.medium
    include_screenshots: bool = False
    include_links: bool = False
    style: str | None = Field(default=None, max_length=200)
    extra_instructions: str | None = Field(default=None, max_length=4000)
    profile: Literal["default"] = "default"
    request_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )

    @field_validator("video_url")
    @classmethod
    def supported_video_url(cls, value: str) -> str:
        detect_video_platform(value)
        return value


class JobResponse(BaseModel):
    job_id: str
    status: TaskStatus
    message: str | None = None
    note_id: str | None = None


class NoteResponse(BaseModel):
    note_id: str
    title: str
    markdown: str
    source_url: str
    platform: str
    video_id: str
    duration_seconds: float
    cover_url: str | None = None


class NoteSearchResult(BaseModel):
    note_id: str
    title: str
    source_url: str
    platform: str
    snippet: str


class NoteSearchResponse(BaseModel):
    query: str
    results: list[NoteSearchResult]


class TranscriptSegmentResponse(BaseModel):
    start: float
    end: float
    text: str


class TranscriptResponse(BaseModel):
    note_id: str
    language: str | None = None
    total_segments: int
    returned_segments: int
    truncated: bool
    segments: list[TranscriptSegmentResponse]
