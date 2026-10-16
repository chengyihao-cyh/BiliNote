# Agent interfaces

BiliNote exposes a narrow agent-facing surface for video-note generation and retrieval. It intentionally excludes provider, cookie, proxy, model-management, deployment, upload, image-proxy, and note-question-answering endpoints.

## Configuration

Set these runtime variables on the BiliNote server:

```bash
BILINOTE_AGENT_TOKEN=<long-random-secret>
BILINOTE_AGENT_PROVIDER_ID=<configured-provider-id>
BILINOTE_AGENT_MODEL_NAME=<configured-model-name>
BILINOTE_AGENT_SEARCH_SCAN_LIMIT=500
# Required only behind a hostname-based reverse proxy, comma separated:
BILINOTE_MCP_ALLOWED_HOSTS=notes.example.com,notes.example.com:*
```

When `BILINOTE_AGENT_TOKEN` is unset, both the Agent REST API and MCP endpoint return `503`. The provider and model are server-side policy; callers cannot select credentials or arbitrary models.

The MCP SDK keeps DNS-rebinding protection enabled. Add every reverse-proxy
hostname to `BILINOTE_MCP_ALLOWED_HOSTS`; add browser origins to
`BILINOTE_MCP_ALLOWED_ORIGINS` only when a browser-based MCP client needs them.

## REST API

All endpoints require `Authorization: Bearer <BILINOTE_AGENT_TOKEN>`.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/jobs` | Queue note generation and return `202` with a `job_id` |
| `GET` | `/api/v1/jobs/{job_id}` | Read the stored job state |
| `GET` | `/api/v1/notes?query=...` | Search sanitized titles and generated Markdown |
| `GET` | `/api/v1/notes/{note_id}` | Read a sanitized completed note |
| `GET` | `/api/v1/notes/{note_id}/transcript` | Read bounded transcript segments |

Use the backend OpenAPI document for request and response schemas. `request_id` makes repeated identical submissions resolve to the same job and rejects reuse with different inputs.

## MCP

The streamable HTTP endpoint is `/mcp/` and uses the same bearer token. It exposes exactly five tools:

- `create_video_note`
- `get_job`
- `get_note`
- `search_notes`
- `lookup_transcript`

The MCP transport is stateless, but generated jobs are durable. Agent and web
requests write their status, request metadata, transcript, and final note to the
same `NOTE_OUTPUT_DIR`; the web console rebuilds its history from that shared
server-side store. Clients should still retain returned identifiers for direct
job polling and retrieval. The MCP surface does not expose BiliNote's internal
RAG question-answering implementation.

## CLI

The dependency-free client uses `BILINOTE_URL` (default `http://127.0.0.1:3015`) and `BILINOTE_AGENT_TOKEN`:

```bash
bin/bilinote generate 'https://www.bilibili.com/video/BV...' --wait
bin/bilinote status <job-id> --wait --json
bin/bilinote search 'keyword' --limit 10
bin/bilinote show <note-id>
bin/bilinote transcript <note-id> --keyword '关键字' --limit 20
```

Place global `--json` before the subcommand. CLI failures use a non-zero exit status and write diagnostics to stderr.
