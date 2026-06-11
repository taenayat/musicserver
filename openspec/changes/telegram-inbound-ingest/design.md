## Context

`telegram.py` today is outbound-only: a single worker drains an upload queue at ≤1 msg/2s, plus primitives `upload_file`, `download_file`, `delete_message`, `test_connection`. It already has `download_file(file_id, dest)` — exactly what ingest needs. The bot is an admin of a private channel (`TELEGRAM_CHANNEL_ID`). The gateway uses the raw Bot API over the shared httpx client; no webhook is configured.

The DB has a generic settings store (`get_setting`/`set_setting`, used for `last_library_scan`), a `telegram_files` table, and `set_telegram_backed`/`add_telegram_file` helpers. `library.is_in_library` provides dedupe, and `library._read_tags` + the Artist/Album folder convention provide placement.

## Goals / Non-Goals

**Goals:**
- A background worker that pulls new channel audio via `getUpdates` and imports it.
- Reliable offset tracking across restarts; dedupe; mark imported files as Telegram-backed.

**Non-Goals:**
- No DM-to-bot ingest in v1 (user chose channel forwarding). The worker can be written to also accept private `message` audio later, but the spec targets `channel_post`.
- No webhook mode.
- No transcoding — store the file as received.

## Decisions

**Long-poll `getUpdates` in a dedicated task.**
Add an inbound worker (separate from the upload worker) that calls `getUpdates` with a stored `offset` and a modest `timeout` (long-poll, e.g. 30s), `allowed_updates=["channel_post","message"]`. Process each update's audio, then advance and persist the offset. Rationale: simplest correct approach with the raw Bot API; no webhook infra; coexists with the outbound uploader. Alternative considered: webhook — rejected (needs public ingress; over-engineered here).

**Persist the offset in settings.**
Store `telegram_update_offset` via `set_setting` after each processed batch so a restart resumes without reprocessing. Rationale: reuses existing settings store; survives restart. (Telegram also drops acknowledged updates server-side once offset advances.)

**Audio detection + placement.**
For each update, look for `audio` (preferred) or a `document` with an audio MIME type. Pull `file_id`, and derive Artist/Album/title from the message's `audio` tags (`performer`, `title`) or the filename; sanitize and place under `/music/<Artist>/<Album>/<file>` using the same conventions as deemix/yt-dlp paths. Download with the existing `download_file`. Rationale: reuse existing helpers and folder layout so the library scanner and dedupe behave identically.

**Index, dedupe, and mark backed.**
After download, read tags (`library._read_tags`), check `library.is_in_library` first — if present, delete the just-downloaded temp/duplicate and skip. Otherwise `upsert_library_track`, then record it as Telegram-backed (`set_telegram_backed` / `add_telegram_file` with the channel msg id + file id) so the outbound backup path never re-uploads it. Finally trigger a Navidrome scan (batched per poll cycle, not per file). Rationale: prevents duplicate files and a re-upload loop.

**Lifespan wiring.**
Start the inbound worker in `lifespan` only when Telegram is configured, and cancel it on shutdown alongside the existing telegram worker. Rationale: consistent lifecycle with the rest of the app.

## Risks / Trade-offs

- **getUpdates conflicts with a webhook** → none is set; if one ever is, `getUpdates` returns 409. Document that webhook mode is unsupported here.
- **Re-upload loop** (import → backup re-uploads → ingest sees it again) → broken by marking imported files Telegram-backed and by `is_in_library` dedupe; the bot's own posts can also be filtered by `from`/`via_bot`.
- **Large files / rate** → ingest is read-side; Telegram bot file download is capped (~20MB via Bot API getFile). Note this limit; larger files may not be retrievable by a bot. Surface a clear log when a file exceeds the limit.
- **Duplicate offset processing on crash mid-batch** → advance offset only after a message is fully handled (or persist per-message); dedupe makes reprocessing harmless anyway.

## Open Questions

- Bot API `getFile` ~20MB download limit may block large/lossless files. Acceptable for v1 (most forwarded tracks are MP3 under the cap); revisit with MTProto/user-bot only if needed.
- Whether to also accept private DMs to the bot — out of scope now, but the worker's `allowed_updates` leaves room.
