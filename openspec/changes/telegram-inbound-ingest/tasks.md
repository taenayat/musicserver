## 1. Inbound worker (backend)

- [x] 1.1 In `telegram.py`, add an inbound worker that long-polls `getUpdates` with a stored offset and `allowed_updates=["channel_post","message"]`.
- [x] 1.2 Add start/stop for the inbound worker mirroring the existing uploader lifecycle.
- [x] 1.3 Persist the update offset via the settings store (`telegram_update_offset`) after each processed batch.

## 2. Audio detection & placement

- [x] 2.1 Detect audio in an update: `audio`, or `document` with an audio MIME type; extract `file_id` and metadata (`performer`/`title`/filename).
- [x] 2.2 Derive `/music/<Artist>/<Album>/<file>` using sanitized metadata and the existing folder conventions.
- [x] 2.3 Download the file with the existing `download_file` helper.
- [x] 2.4 Log clearly when a file exceeds the Bot API getFile size limit and skip it.

## 3. Index, dedupe, mark backed

- [x] 3.1 Read tags with `library._read_tags`; check `library.is_in_library` and skip + remove the temp file if already present.
- [x] 3.2 `upsert_library_track` for new imports.
- [x] 3.3 Record imported files as Telegram-backed (`set_telegram_backed` / `add_telegram_file`) so they're not re-uploaded.
- [x] 3.4 Filter out the bot's own posts to avoid an import/re-upload loop.

## 4. Scan & lifecycle

- [x] 4.1 Trigger a Navidrome scan once per poll cycle that imported anything.
- [x] 4.2 In `main.py` lifespan, start the inbound worker only when Telegram is configured; cancel on shutdown.

## 5. Verify

- [ ] 5.1 Forward an audio message into the channel; confirm it imports, indexes, and appears in Symfonium after sync.
- [ ] 5.2 Upload an audio file directly to the channel; confirm import.
- [ ] 5.3 Restart the gateway; confirm prior messages are not reprocessed.
- [ ] 5.4 Forward a duplicate of an existing library track; confirm it is skipped.
