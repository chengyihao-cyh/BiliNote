import asyncio
import json
from types import SimpleNamespace

import pytest
from app.core.agent_auth import validate_agent_authorization
from app.enmus.task_status_enums import TaskStatus
from app.mcp_server import mcp, mcp_http_app
from app.models.agent_api import CreateVideoNoteRequest
from app.routers.agent import router as agent_router
from app.services import agent_notes, note_jobs
from app.services.agent_notes import AgentConflictError, AgentNoteService
from app.services.provider import ProviderService
from app.services.task_history import (
    delete_task_history,
    list_task_history,
    save_task_request,
)
from fastapi import HTTPException
from starlette.testclient import TestClient


@pytest.fixture
def agent_service(tmp_path, monkeypatch):
    monkeypatch.setattr(note_jobs, "NOTE_OUTPUT_DIR", tmp_path)
    monkeypatch.setenv("BILINOTE_AGENT_PROVIDER_ID", "provider-1")
    monkeypatch.setenv("BILINOTE_AGENT_MODEL_NAME", "model-1")
    monkeypatch.setattr(
        agent_notes.TranscriberConfigManager,
        "is_model_ready",
        lambda self: {"ready": True},
    )
    submitted = []
    monkeypatch.setattr(
        note_jobs, "submit_note_task", lambda **kwargs: submitted.append(kwargs)
    )
    return AgentNoteService(), submitted, tmp_path


def test_agent_token_is_required_and_compared(monkeypatch):
    monkeypatch.delenv("BILINOTE_AGENT_TOKEN", raising=False)
    with pytest.raises(HTTPException) as disabled:
        validate_agent_authorization(None)
    assert disabled.value.status_code == 503

    monkeypatch.setenv("BILINOTE_AGENT_TOKEN", "test-secret")
    with pytest.raises(HTTPException) as unauthorized:
        validate_agent_authorization("Bearer wrong-secret")
    assert unauthorized.value.status_code == 401
    validate_agent_authorization("Bearer test-secret")


def test_create_job_is_idempotent_for_request_id(agent_service, monkeypatch):
    service, submitted, output_dir = agent_service
    request = CreateVideoNoteRequest(
        video_url="https://youtu.be/abcdefghijk",
        request_id="request-123",
    )

    first = service.create_job(request)
    monkeypatch.delenv("BILINOTE_AGENT_PROVIDER_ID")
    monkeypatch.delenv("BILINOTE_AGENT_MODEL_NAME")
    second = service.create_job(request)

    assert first == second
    assert first.status == TaskStatus.PENDING
    assert len(submitted) == 1
    assert submitted[0]["platform"] == "youtube"
    assert submitted[0]["provider_id"] == "provider-1"
    stored_request = json.loads(
        (output_dir / f"{first.job_id}.request.json").read_text(encoding="utf-8")
    )
    assert stored_request["source"] == "mcp"
    assert stored_request["form_data"]["video_url"] == "https://youtu.be/abcdefghijk"


def test_request_id_reuse_with_different_inputs_is_rejected(agent_service):
    service, _, _ = agent_service
    service.create_job(
        CreateVideoNoteRequest(
            video_url="https://youtu.be/abcdefghijk",
            request_id="request-123",
        )
    )

    with pytest.raises(AgentConflictError):
        service.create_job(
            CreateVideoNoteRequest(
                video_url="https://youtu.be/lmnopqrstuv",
                request_id="request-123",
            )
        )


def test_note_and_transcript_are_sanitized_and_bounded(agent_service):
    service, _, output_dir = agent_service
    job_id = "f504a5a9-9d68-4ae6-97aa-bad5d418b271"
    note_payload = {
        "markdown": "# Useful note",
        "audio_meta": {
            "file_path": "/private/audio.mp3",
            "title": "Video title",
            "duration": 120.5,
            "cover_url": "https://example.com/cover.jpg",
            "platform": "youtube",
            "video_id": "abcdefghijk",
            "raw_info": {
                "webpage_url": "https://youtu.be/abcdefghijk",
                "private_debug_value": "must not escape",
            },
        },
        "transcript": {
            "language": "en",
            "full_text": "alpha beta gamma",
            "raw": {"provider": "private"},
            "segments": [
                {"start": 0, "end": 5, "text": "alpha"},
                {"start": 5, "end": 10, "text": "beta"},
                {"start": 10, "end": 15, "text": "gamma beta"},
            ],
        },
    }
    (output_dir / f"{job_id}.json").write_text(
        json.dumps(note_payload), encoding="utf-8"
    )

    note = service.get_note(job_id)
    assert note.title == "Video title"
    assert note.source_url == "https://youtu.be/abcdefghijk"
    assert "file_path" not in note.model_dump()
    assert "raw_info" not in note.model_dump()

    transcript = service.lookup_transcript(job_id, keyword="beta", limit=1)
    assert transcript.total_segments == 3
    assert transcript.returned_segments == 1
    assert transcript.truncated is True
    assert transcript.segments[0].text == "beta"
    assert "full_text" not in transcript.model_dump()
    assert "raw" not in transcript.model_dump()

    search = service.search_notes("useful", limit=5)
    assert len(search.results) == 1
    assert search.results[0].note_id == job_id
    assert search.results[0].source_url == "https://youtu.be/abcdefghijk"

    legacy_task = list_task_history()[0]
    assert legacy_task["id"] == job_id
    assert legacy_task["source"] == "legacy"
    assert legacy_task["formData"]["video_url"] == "https://youtu.be/abcdefghijk"


def test_server_history_lists_and_deletes_agent_notes(agent_service):
    service, _, output_dir = agent_service
    response = service.create_job(
        CreateVideoNoteRequest(video_url="https://youtu.be/abcdefghijk")
    )
    result = {
        "markdown": "# Stored note",
        "audio_meta": {
            "title": "Stored title",
            "platform": "youtube",
            "video_id": "abcdefghijk",
            "cover_url": "https://example.com/cover.jpg",
            "raw_info": {"webpage_url": "https://youtu.be/abcdefghijk"},
        },
        "transcript": {
            "language": "en",
            "full_text": "stored transcript",
            "raw": None,
            "segments": [{"start": 0, "end": 1, "text": "stored"}],
        },
    }
    (output_dir / f"{response.job_id}.json").write_text(
        json.dumps(result), encoding="utf-8"
    )
    note_jobs.write_job_status(response.job_id, TaskStatus.SUCCESS)

    web_task_id = "f504a5a9-9d68-4ae6-97aa-bad5d418b271"
    save_task_request(
        web_task_id,
        source="web",
        form_data={
            "video_url": "https://youtu.be/lmnopqrstuv",
            "platform": "youtube",
        },
    )
    (output_dir / f"{web_task_id}.json").write_text(
        json.dumps({**result, "markdown": "# Web note"}), encoding="utf-8"
    )
    note_jobs.write_job_status(web_task_id, TaskStatus.SUCCESS)

    history = list_task_history()
    assert len(history) == 2
    assert {task["source"] for task in history} == {"mcp", "web"}
    agent_task = next(task for task in history if task["id"] == response.job_id)
    assert agent_task["markdown"] == "# Stored note"
    assert agent_task["transcript"]["full_text"] == "stored transcript"

    summary = next(
        task
        for task in list_task_history(include_results=False)
        if task["id"] == response.job_id
    )
    assert summary["audioMeta"]["title"] == "Stored title"
    assert summary["markdown"] == ""
    assert summary["transcript"]["segments"] == []

    assert delete_task_history(response.job_id) is True
    assert delete_task_history(web_task_id) is True
    assert list_task_history() == []


def test_server_history_ignores_and_deletes_orphan_markdown_status(agent_service):
    _, _, output_dir = agent_service
    task_id = "fef835bc-b5b5-530e-b4a1-6cba5be2c503"
    orphan_status = output_dir / f"{task_id}_markdown.status.json"
    orphan_status.write_text(
        json.dumps({"status": "FAILED", "message": "formatting failed"}),
        encoding="utf-8",
    )

    assert list_task_history() == []
    assert delete_task_history(task_id) is True
    assert not orphan_status.exists()


def test_mcp_exposes_only_supported_note_tools():
    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == {
        "create_video_note",
        "get_job",
        "get_note",
        "search_notes",
        "lookup_transcript",
    }
    assert all(tool.outputSchema for tool in tools)
    by_name = {tool.name: tool for tool in tools}
    assert by_name["create_video_note"].annotations.readOnlyHint is False
    assert by_name["create_video_note"].annotations.openWorldHint is True
    assert all(
        by_name[name].annotations.readOnlyHint is True
        for name in ("get_job", "get_note", "search_notes", "lookup_transcript")
    )


def test_mcp_initialize_requires_authentication(monkeypatch):
    monkeypatch.setenv("BILINOTE_AGENT_TOKEN", "test-secret")
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1.0"},
        },
    }

    with TestClient(mcp_http_app, base_url="http://localhost") as client:
        assert client.post("/", json=payload).status_code == 401
        response = client.post(
            "/",
            json=payload,
            headers={
                "Authorization": "Bearer test-secret",
                "Accept": "application/json, text/event-stream",
            },
        )

    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "bilinote"


def test_agent_openapi_contains_no_question_answering_endpoint():
    paths = {route.path for route in agent_router.routes}

    assert "/v1/jobs" in paths
    assert "/v1/jobs/{job_id}" in paths
    assert "/v1/notes" in paths
    assert "/v1/notes/{note_id}" in paths
    assert "/v1/notes/{note_id}/transcript" in paths
    assert not any("question" in path or "ask" in path for path in paths)


def test_safe_provider_list_masks_api_keys(monkeypatch):
    row = SimpleNamespace(
        id="provider-1",
        name="Provider",
        logo="custom",
        type="custom",
        enabled=1,
        base_url="https://example.com/v1",
        api_key="secret-api-key",
        created_at=None,
    )
    monkeypatch.setattr("app.services.provider.get_all_providers", lambda: [row])

    result = ProviderService.get_all_providers_safe()

    assert result[0]["api_key"] != "secret-api-key"
    assert result[0]["api_key"].startswith("secr")
