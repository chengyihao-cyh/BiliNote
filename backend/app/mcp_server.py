import os

from app.core.agent_auth import AgentTokenMiddleware
from app.enmus.note_enums import DownloadQuality
from app.models.agent_api import (
    CreateVideoNoteRequest,
    JobResponse,
    NoteResponse,
    NoteSearchResponse,
    TranscriptResponse,
)
from app.services.agent_notes import agent_note_service
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations


def _csv_env(name: str) -> list[str]:
    return [value.strip() for value in os.getenv(name, "").split(",") if value.strip()]


allowed_hosts = [
    "127.0.0.1",
    "127.0.0.1:*",
    "localhost",
    "localhost:*",
    "[::1]",
    "[::1]:*",
    *_csv_env("BILINOTE_MCP_ALLOWED_HOSTS"),
]
allowed_origins = [
    "http://127.0.0.1:*",
    "http://localhost:*",
    "http://[::1]:*",
    *_csv_env("BILINOTE_MCP_ALLOWED_ORIGINS"),
]

mcp = FastMCP(
    name="bilinote",
    instructions=(
        "Search existing notes before creating duplicate work. To create one, poll get_job "
        "until it succeeds or fails, then read the note. "
        "Use lookup_transcript only when the full note lacks details. BiliNote does not answer "
        "questions about notes; reason over the returned note and transcript yourself."
    ),
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    ),
)


@mcp.tool(
    title="Create video note",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
    structured_output=True,
)
def create_video_note(
    video_url: str,
    quality: DownloadQuality = DownloadQuality.medium,
    include_screenshots: bool = False,
    include_links: bool = False,
    style: str | None = None,
    extra_instructions: str | None = None,
    request_id: str | None = None,
) -> JobResponse:
    """Queue generation of a structured Markdown note from a supported public video URL."""
    return agent_note_service.create_job(
        CreateVideoNoteRequest(
            video_url=video_url,
            quality=quality,
            include_screenshots=include_screenshots,
            include_links=include_links,
            style=style,
            extra_instructions=extra_instructions,
            request_id=request_id,
        )
    )


@mcp.tool(
    title="Get note job",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    structured_output=True,
)
def get_job(job_id: str) -> JobResponse:
    """Get the current state of a video-note job."""
    return agent_note_service.get_job(job_id)


@mcp.tool(
    title="Get video note",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    structured_output=True,
)
def get_note(note_id: str) -> NoteResponse:
    """Read a completed video note without internal paths, model settings, or raw provider data."""
    return agent_note_service.get_note(note_id)


@mcp.tool(
    title="Search video notes",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    structured_output=True,
)
def search_notes(query: str = "", limit: int = 10) -> NoteSearchResponse:
    """Find previously completed notes by title or generated Markdown content."""
    return agent_note_service.search_notes(query=query, limit=limit)


@mcp.tool(
    title="Look up video transcript",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    structured_output=True,
)
def lookup_transcript(
    note_id: str,
    start_time: float | None = None,
    end_time: float | None = None,
    keyword: str | None = None,
    limit: int = 50,
) -> TranscriptResponse:
    """Read bounded transcript segments by time range or keyword from a completed note."""
    return agent_note_service.lookup_transcript(
        note_id,
        start_time=start_time,
        end_time=end_time,
        keyword=keyword,
        limit=limit,
    )


mcp_starlette_app = mcp.streamable_http_app()
mcp_http_app = AgentTokenMiddleware(mcp_starlette_app)
