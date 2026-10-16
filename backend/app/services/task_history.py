import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.enmus.task_status_enums import TaskStatus
from app.services import note_jobs


class TaskHistoryError(Exception):
    pass


def _task_id(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise TaskHistoryError("Task was not found") from exc


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def save_task_request(
    task_id: str,
    *,
    source: str,
    form_data: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist creation metadata shared by web and agent-created tasks."""
    task_id = _task_id(task_id)
    request_path = note_jobs.NOTE_OUTPUT_DIR / f"{task_id}.request.json"
    stored = _read_json(request_path) if request_path.exists() else {}
    created_at = stored.get("created_at") or datetime.now(timezone.utc).isoformat()

    payload = {
        **stored,
        **(metadata or {}),
        "job_id": task_id,
        "source": stored.get("source") or source,
        "created_at": created_at,
        "video_url": form_data.get("video_url") or stored.get("video_url") or "",
        "platform": form_data.get("platform") or stored.get("platform") or "",
        "form_data": form_data,
    }
    _write_json_atomic(request_path, payload)


def list_task_history(*, include_results: bool = True) -> list[dict[str, Any]]:
    output_dir = note_jobs.NOTE_OUTPUT_DIR
    if not output_dir.exists():
        return []

    task_ids: set[str] = set()
    for path in output_dir.glob("*.json"):
        candidate = path.name.split(".", 1)[0].split("_", 1)[0]
        try:
            task_ids.add(str(uuid.UUID(candidate)))
        except ValueError:
            continue

    tasks = [
        _load_task(task_id, include_results=include_results) for task_id in task_ids
    ]
    tasks.sort(key=lambda task: task["createdAt"], reverse=True)
    return tasks


def delete_task_history(task_id: str) -> bool:
    task_id = _task_id(task_id)
    output_dir = note_jobs.NOTE_OUTPUT_DIR
    paths = (
        output_dir / f"{task_id}.json",
        output_dir / f"{task_id}.status.json",
        output_dir / f"{task_id}.request.json",
        output_dir / f"{task_id}_audio.json",
        output_dir / f"{task_id}_transcript.json",
        output_dir / f"{task_id}_markdown.md",
    )
    deleted = False
    for path in paths:
        if path.exists():
            path.unlink()
            deleted = True
    return deleted


def _load_task(task_id: str, *, include_results: bool) -> dict[str, Any]:
    output_dir = note_jobs.NOTE_OUTPUT_DIR
    request_path = output_dir / f"{task_id}.request.json"
    status_path = output_dir / f"{task_id}.status.json"
    result_path = output_dir / f"{task_id}.json"

    request = _read_json(request_path)
    status_data = _read_json(status_path)
    result = _read_json(result_path)
    audio_meta = result.get("audio_meta") or {}

    status = status_data.get("status")
    if result and status != TaskStatus.FAILED.value:
        status = TaskStatus.SUCCESS.value
    if status not in {item.value for item in TaskStatus}:
        status = TaskStatus.PENDING.value

    form_data = request.get("form_data") or _inferred_form_data(request, audio_meta)
    platform = (
        form_data.get("platform")
        or audio_meta.get("platform")
        or request.get("platform")
        or ""
    )
    created_at = request.get("created_at") or _created_at(
        request_path, status_path, result_path
    )
    updated_at = _updated_at(request_path, status_path, result_path)
    public_audio_meta = audio_meta
    if audio_meta and not include_results:
        public_audio_meta = {
            "cover_url": audio_meta.get("cover_url") or "",
            "duration": audio_meta.get("duration") or 0,
            "file_path": "",
            "platform": audio_meta.get("platform") or platform,
            "raw_info": None,
            "title": audio_meta.get("title") or "",
            "video_id": audio_meta.get("video_id") or "",
        }

    return {
        "id": task_id,
        "status": status,
        "createdAt": created_at,
        "updatedAt": updated_at,
        "source": request.get("source") or "legacy",
        "formData": form_data,
        "markdown": (result.get("markdown") if include_results else "") or "",
        "transcript": (result.get("transcript") if include_results else None)
        or {"full_text": "", "language": "", "raw": None, "segments": []},
        "audioMeta": public_audio_meta
        or {
            "cover_url": "",
            "duration": 0,
            "file_path": "",
            "platform": platform,
            "raw_info": None,
            "title": "",
            "video_id": "",
        },
        "platform": platform,
    }


def _inferred_form_data(
    request: dict[str, Any], audio_meta: dict[str, Any]
) -> dict[str, Any]:
    raw_info = audio_meta.get("raw_info") or {}
    return {
        "video_url": request.get("video_url") or raw_info.get("webpage_url") or "",
        "platform": request.get("platform") or audio_meta.get("platform") or "",
        "quality": "medium",
        "screenshot": False,
        "link": False,
        "model_name": "",
        "provider_id": "",
        "format": [],
        "style": "minimal",
        "extras": "",
        "video_understanding": False,
        "video_interval": 6,
        "grid_size": [2, 2],
    }


def _created_at(*paths: Path) -> str:
    timestamps = [path.stat().st_mtime for path in paths if path.exists()]
    timestamp = min(timestamps) if timestamps else 0
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _updated_at(*paths: Path) -> str:
    timestamps = [path.stat().st_mtime for path in paths if path.exists()]
    timestamp = max(timestamps) if timestamps else 0
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
