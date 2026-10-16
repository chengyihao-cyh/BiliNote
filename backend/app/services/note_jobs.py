import atexit
import json
import os
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from app.enmus.note_enums import DownloadQuality
from app.enmus.task_status_enums import TaskStatus
from app.utils.logger import get_logger

NOTE_OUTPUT_DIR = Path(os.getenv("NOTE_OUTPUT_DIR", "note_results"))
logger = get_logger(__name__)
_job_executor = ThreadPoolExecutor(
    max_workers=int(os.getenv("TASK_MAX_WORKERS", "3")),
    thread_name_prefix="bilinote-job",
)
atexit.register(_job_executor.shutdown, wait=False, cancel_futures=True)


def save_note_to_file(task_id: str, note) -> None:
    NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = NOTE_OUTPUT_DIR / f"{task_id}.json"
    target.write_text(
        json.dumps(asdict(note), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def persist_prefetched_transcript(task_id: str, transcript: dict) -> None:
    segments = transcript.get("segments") or []
    cleaned_segments = []
    for segment in segments:
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        cleaned_segments.append(
            {
                "start": float(segment.get("start", 0)),
                "end": float(segment.get("end", 0)),
                "text": text,
            }
        )
    if not cleaned_segments:
        raise ValueError("prefetched_transcript has no usable segments")

    payload = {
        "language": transcript.get("language") or "zh",
        "full_text": transcript.get("full_text")
        or " ".join(segment["text"] for segment in cleaned_segments),
        "segments": cleaned_segments,
    }
    NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = NOTE_OUTPUT_DIR / f"{task_id}_transcript.json"
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(
        f"Saved prefetched transcript: {target} ({len(cleaned_segments)} segments)"
    )


def write_job_status(
    task_id: str, status: TaskStatus, message: str | None = None
) -> None:
    NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = NOTE_OUTPUT_DIR / f"{task_id}.status.json"
    temporary = target.with_suffix(".tmp")
    payload = {"status": status.value}
    if message:
        payload["message"] = message
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(target)


def run_note_task(
    task_id: str,
    video_url: str,
    platform: str,
    quality: DownloadQuality,
    link: bool = False,
    screenshot: bool = False,
    model_name: str | None = None,
    provider_id: str | None = None,
    formats: list | None = None,
    style: str | None = None,
    extras: str | None = None,
    video_understanding: bool = False,
    video_interval: int = 0,
    grid_size: list | None = None,
) -> None:
    from app.services.note import NoteGenerator

    if not model_name or not provider_id:
        raise ValueError("model_name and provider_id are required")

    logger.info(f"Job started (task_id={task_id})")
    note = NoteGenerator().generate(
        video_url=video_url,
        platform=platform,
        quality=quality,
        task_id=task_id,
        model_name=model_name,
        provider_id=provider_id,
        link=link,
        _format=formats or [],
        style=style,
        extras=extras,
        screenshot=screenshot,
        video_understanding=video_understanding,
        video_interval=video_interval,
        grid_size=grid_size or [],
    )
    if not note or not note.markdown:
        logger.warning(f"Job produced no note (task_id={task_id})")
        write_job_status(
            task_id, TaskStatus.FAILED, "Note generation produced no content"
        )
        return

    save_note_to_file(task_id, note)
    write_job_status(task_id, TaskStatus.SUCCESS)
    try:
        from app.services.vector_store import VectorStoreManager

        VectorStoreManager().index_task(task_id)
    # Indexing is optional post-processing; its backend errors must not discard the note.
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Vector indexing failed without failing the note job: {exc}")


def submit_note_task(**kwargs) -> Future:
    task_id = kwargs["task_id"]
    future = _job_executor.submit(run_note_task, **kwargs)

    def record_unhandled_failure(completed: Future) -> None:
        try:
            completed.result()
        except Exception as exc:
            logger.exception(f"Unhandled note job failure (task_id={task_id})")
            write_job_status(task_id, TaskStatus.FAILED, str(exc))

    future.add_done_callback(record_unhandled_failure)
    return future
