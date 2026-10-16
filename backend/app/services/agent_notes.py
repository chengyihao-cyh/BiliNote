import hashlib
import json
import os
import threading
import uuid
from pathlib import Path

from app.enmus.task_status_enums import TaskStatus
from app.models.agent_api import (
    CreateVideoNoteRequest,
    JobResponse,
    NoteResponse,
    NoteSearchResponse,
    NoteSearchResult,
    TranscriptResponse,
    TranscriptSegmentResponse,
)
from app.services import note_jobs
from app.services.transcriber_config_manager import TranscriberConfigManager
from app.utils.url_parser import normalize_video_url
from app.validators.video_url_validator import detect_video_platform


class AgentNoteError(Exception):
    pass


class AgentConfigurationError(AgentNoteError):
    pass


class AgentConflictError(AgentNoteError):
    pass


class AgentNotFoundError(AgentNoteError):
    pass


class AgentNotReadyError(AgentNoteError):
    pass


_request_lock = threading.Lock()
_request_namespace = uuid.UUID("f16af05f-7f7e-4ce1-a9d5-e7bc3d27ec9a")


def _output_dir() -> Path:
    return note_jobs.NOTE_OUTPUT_DIR


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentNoteError(f"Cannot read stored note data: {path.name}") from exc


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _validated_job_id(job_id: str) -> str:
    try:
        return str(uuid.UUID(job_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AgentNotFoundError("Job was not found") from exc


def _generation_target() -> tuple[str, str]:
    provider_id = os.getenv("BILINOTE_AGENT_PROVIDER_ID", "").strip()
    model_name = os.getenv("BILINOTE_AGENT_MODEL_NAME", "").strip()
    if not provider_id or not model_name:
        raise AgentConfigurationError(
            "Agent generation is disabled; configure BILINOTE_AGENT_PROVIDER_ID "
            "and BILINOTE_AGENT_MODEL_NAME"
        )
    return provider_id, model_name


class AgentNoteService:
    def create_job(self, request: CreateVideoNoteRequest) -> JobResponse:
        video_url = request.video_url
        platform = detect_video_platform(video_url)
        if platform == "bilibili":
            video_url = normalize_video_url(video_url)

        request_payload = request.model_dump(mode="json", exclude={"request_id"})
        request_payload["video_url"] = video_url
        fingerprint = hashlib.sha256(
            json.dumps(request_payload, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        job_id = (
            str(uuid.uuid5(_request_namespace, request.request_id))
            if request.request_id
            else str(uuid.uuid4())
        )
        request_path = _output_dir() / f"{job_id}.request.json"

        with _request_lock:
            if request_path.exists():
                stored = _read_json(request_path)
                if stored.get("fingerprint") != fingerprint:
                    raise AgentConflictError(
                        "request_id was already used with different inputs"
                    )
                return self.get_job(job_id)

            provider_id, model_name = _generation_target()
            readiness = TranscriberConfigManager().is_model_ready()
            if not readiness["ready"]:
                raise AgentNotReadyError(readiness["reason"])

            _write_json_atomic(
                request_path,
                {
                    "job_id": job_id,
                    "fingerprint": fingerprint,
                    "video_url": video_url,
                    "platform": platform,
                    "profile": request.profile,
                },
            )
            note_jobs.write_job_status(job_id, TaskStatus.PENDING, "Queued")

            formats = []
            if request.include_links:
                formats.append("link")
            if request.include_screenshots:
                formats.append("screenshot")
            note_jobs.submit_note_task(
                task_id=job_id,
                video_url=video_url,
                platform=platform,
                quality=request.quality,
                link=request.include_links,
                screenshot=request.include_screenshots,
                model_name=model_name,
                provider_id=provider_id,
                formats=formats,
                style=request.style,
                extras=request.extra_instructions,
            )

        return JobResponse(job_id=job_id, status=TaskStatus.PENDING, message="Queued")

    def get_job(self, job_id: str) -> JobResponse:
        job_id = _validated_job_id(job_id)
        status_path = _output_dir() / f"{job_id}.status.json"
        result_path = _output_dir() / f"{job_id}.json"
        request_path = _output_dir() / f"{job_id}.request.json"
        if (
            not status_path.exists()
            and not result_path.exists()
            and not request_path.exists()
        ):
            raise AgentNotFoundError("Job was not found")

        if status_path.exists():
            payload = _read_json(status_path)
            try:
                current_status = TaskStatus(payload.get("status"))
            except ValueError as exc:
                raise AgentNoteError("Stored job has an invalid status") from exc
            message = payload.get("message")
        elif result_path.exists():
            current_status = TaskStatus.SUCCESS
            message = None
        else:
            current_status = TaskStatus.PENDING
            message = "Queued"

        if current_status == TaskStatus.SUCCESS and not result_path.exists():
            current_status = TaskStatus.SAVING
            message = "Finalizing note"
        note_id = job_id if current_status == TaskStatus.SUCCESS else None
        return JobResponse(
            job_id=job_id,
            status=current_status,
            message=message,
            note_id=note_id,
        )

    def get_note(self, note_id: str) -> NoteResponse:
        note_id = _validated_job_id(note_id)
        result_path = _output_dir() / f"{note_id}.json"
        if not result_path.exists():
            raise AgentNotFoundError("Completed note was not found")

        data = _read_json(result_path)
        audio_meta = data.get("audio_meta") or {}
        raw_info = audio_meta.get("raw_info") or {}
        request_path = _output_dir() / f"{note_id}.request.json"
        request_data = _read_json(request_path) if request_path.exists() else {}
        source_url = raw_info.get("webpage_url") or request_data.get("video_url") or ""
        return NoteResponse(
            note_id=note_id,
            title=audio_meta.get("title") or raw_info.get("title") or "Untitled video",
            markdown=data.get("markdown") or "",
            source_url=source_url,
            platform=audio_meta.get("platform") or request_data.get("platform") or "",
            video_id=audio_meta.get("video_id") or "",
            duration_seconds=float(audio_meta.get("duration") or 0),
            cover_url=audio_meta.get("cover_url"),
        )

    def search_notes(self, query: str = "", limit: int = 10) -> NoteSearchResponse:
        if limit < 1 or limit > 50:
            raise AgentConflictError("limit must be between 1 and 50")

        normalized_query = query.casefold().strip()
        output_dir = _output_dir()
        if not output_dir.exists():
            return NoteSearchResponse(query=query, results=[])

        candidates = []
        for path in output_dir.glob("*.json"):
            try:
                uuid.UUID(path.stem)
            except ValueError:
                continue
            candidates.append(path)
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)

        scan_limit = max(1, int(os.getenv("BILINOTE_AGENT_SEARCH_SCAN_LIMIT", "500")))
        results = []
        for path in candidates[:scan_limit]:
            try:
                note = self.get_note(path.stem)
            except AgentNoteError:
                continue
            searchable = f"{note.title}\n{note.markdown}".casefold()
            if normalized_query and normalized_query not in searchable:
                continue
            results.append(
                NoteSearchResult(
                    note_id=note.note_id,
                    title=note.title,
                    source_url=note.source_url,
                    platform=note.platform,
                    snippet=_note_snippet(note.markdown, normalized_query),
                )
            )
            if len(results) >= limit:
                break
        return NoteSearchResponse(query=query, results=results)

    def lookup_transcript(
        self,
        note_id: str,
        *,
        start_time: float | None = None,
        end_time: float | None = None,
        keyword: str | None = None,
        limit: int = 50,
    ) -> TranscriptResponse:
        if start_time is not None and end_time is not None and start_time > end_time:
            raise AgentConflictError("start_time must not be greater than end_time")
        if limit < 1 or limit > 200:
            raise AgentConflictError("limit must be between 1 and 200")

        note = self._load_note_data(note_id)
        transcript = note.get("transcript") or {}
        all_segments = transcript.get("segments") or []
        filtered = all_segments
        if start_time is not None:
            filtered = [
                segment
                for segment in filtered
                if float(segment.get("end", 0)) >= start_time
            ]
        if end_time is not None:
            filtered = [
                segment
                for segment in filtered
                if float(segment.get("start", 0)) <= end_time
            ]
        if keyword:
            query = keyword.casefold().strip()
            filtered = [
                segment
                for segment in filtered
                if query in str(segment.get("text", "")).casefold()
            ]

        truncated = len(filtered) > limit
        selected = filtered[:limit]
        return TranscriptResponse(
            note_id=_validated_job_id(note_id),
            language=transcript.get("language"),
            total_segments=len(all_segments),
            returned_segments=len(selected),
            truncated=truncated,
            segments=[
                TranscriptSegmentResponse(
                    start=float(segment.get("start", 0)),
                    end=float(segment.get("end", 0)),
                    text=str(segment.get("text", "")),
                )
                for segment in selected
            ],
        )

    def _load_note_data(self, note_id: str) -> dict:
        note_id = _validated_job_id(note_id)
        result_path = _output_dir() / f"{note_id}.json"
        if not result_path.exists():
            raise AgentNotFoundError("Completed note was not found")
        return _read_json(result_path)


agent_note_service = AgentNoteService()


def _note_snippet(markdown: str, normalized_query: str, length: int = 280) -> str:
    compact = " ".join(markdown.split())
    if not compact:
        return ""
    if not normalized_query:
        return compact[:length]
    position = compact.casefold().find(normalized_query)
    if position < 0:
        return compact[:length]
    start = max(0, position - length // 3)
    end = min(len(compact), start + length)
    prefix = "..." if start else ""
    suffix = "..." if end < len(compact) else ""
    return f"{prefix}{compact[start:end]}{suffix}"
