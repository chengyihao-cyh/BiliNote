---
name: bilinote-video-notes
description: Create and retrieve structured notes or transcript excerpts from supported Bilibili, YouTube, Douyin, and Kuaishou video URLs through BiliNote.
---

Use BiliNote when the user wants a video converted into a structured note or needs evidence from a video's transcript.

Prefer the BiliNote MCP tools when they are available. Otherwise use `bin/bilinote`; it requires `BILINOTE_URL` and `BILINOTE_AGENT_TOKEN` in the environment.

1. When the user refers to an existing note, call `search_notes` before creating work. Otherwise call `create_video_note` once with the video URL. Supply a stable `request_id` when retrying the same user request.
2. Keep the returned `job_id`. Poll `get_job` at a moderate interval until the state is `SUCCESS` or `FAILED`; do not submit another job merely because generation is slow.
3. On success, call `get_note` with `note_id`. Treat its `source_url` as the canonical source.
4. Use `lookup_transcript` only when the note lacks a detail needed for the user's request. Bound transcript reads with a time range, keyword, or modest limit.
5. Answer questions by reasoning over the returned note and transcript. BiliNote intentionally does not provide an `ask_note` tool.

Report failed jobs with their returned message. Do not claim that a queued or running job completed, invent missing transcript content, or expose authentication tokens and server configuration.
