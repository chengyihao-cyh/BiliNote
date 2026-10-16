from typing import Annotated

from app.core.agent_auth import require_agent_token
from app.models.agent_api import (
    CreateVideoNoteRequest,
    JobResponse,
    NoteResponse,
    NoteSearchResponse,
    TranscriptResponse,
)
from app.services.agent_notes import (
    AgentConfigurationError,
    AgentConflictError,
    AgentNoteError,
    AgentNotFoundError,
    AgentNotReadyError,
    agent_note_service,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status

router = APIRouter(
    prefix="/v1",
    tags=["Agent API"],
    dependencies=[Depends(require_agent_token)],
)


def _raise_http_error(exc: AgentNoteError) -> None:
    if isinstance(exc, AgentNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, AgentConflictError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, AgentNotReadyError):
        code = status.HTTP_425_TOO_EARLY
    elif isinstance(exc, AgentConfigurationError):
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        code = status.HTTP_500_INTERNAL_SERVER_ERROR
    raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post(
    "/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="create_video_note_job",
)
def create_video_note(request: CreateVideoNoteRequest) -> JobResponse:
    """Queue a video-to-note job using the server's configured agent profile."""
    try:
        return agent_note_service.create_job(request)
    except AgentNoteError as exc:
        _raise_http_error(exc)


@router.get(
    "/jobs/{job_id}", response_model=JobResponse, operation_id="get_video_note_job"
)
def get_job(job_id: str) -> JobResponse:
    try:
        return agent_note_service.get_job(job_id)
    except AgentNoteError as exc:
        _raise_http_error(exc)


@router.get(
    "/notes/{note_id}", response_model=NoteResponse, operation_id="get_video_note"
)
def get_note(note_id: str) -> NoteResponse:
    try:
        return agent_note_service.get_note(note_id)
    except AgentNoteError as exc:
        _raise_http_error(exc)


@router.get(
    "/notes", response_model=NoteSearchResponse, operation_id="search_video_notes"
)
def search_notes(
    query: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> NoteSearchResponse:
    try:
        return agent_note_service.search_notes(query=query, limit=limit)
    except AgentNoteError as exc:
        _raise_http_error(exc)


@router.get(
    "/notes/{note_id}/transcript",
    response_model=TranscriptResponse,
    operation_id="lookup_video_transcript",
)
def lookup_transcript(
    note_id: str,
    start_time: Annotated[float | None, Query(ge=0)] = None,
    end_time: Annotated[float | None, Query(ge=0)] = None,
    keyword: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> TranscriptResponse:
    try:
        return agent_note_service.lookup_transcript(
            note_id,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            limit=limit,
        )
    except AgentNoteError as exc:
        _raise_http_error(exc)
