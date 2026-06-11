## Why

Telegram is currently one-way: the gateway uploads downloads to a private channel for cold storage but never reads from it. The user wants to drop music in from the other direction — forward or upload an audio file into the channel and then listen to it in Symfonium. That requires the gateway to watch the channel for incoming audio and import it into the library.

## What Changes

- **Add inbound Telegram ingest** — a background worker polls the bot for new channel messages, detects audio (uploaded or forwarded), downloads the file via the Telegram file API into `/music/<Artist>/<Album>/`, indexes it into the library, and triggers a Navidrome scan so it becomes playable.
- Ingest path is **the backup channel** (per decision): the bot, already an admin of the channel, receives `channel_post` updates for audio posted/forwarded there.
- Imported files are de-duplicated against the existing library (don't re-import something already present) and recorded so they aren't redundantly re-uploaded back to Telegram.

## Capabilities

### New Capabilities
- `telegram-inbound-ingest`: the gateway watches its Telegram channel for incoming audio messages and imports them into the music library, making them playable in Symfonium.

### Modified Capabilities
- None (no pre-existing specs).

## Impact

- Backend: `telegram.py` (new inbound poll loop using `getUpdates`, audio detection, reuse of `download_file`), `main.py` (start the inbound worker in lifespan; track the update offset), `library.py`/`db.py` (index imported files, dedupe, mark as telegram-sourced to avoid re-upload).
- New consideration: `getUpdates` long-polling alongside the existing outbound uploader; must not conflict with webhook (none set) and must persist the last-seen update offset so restarts don't reprocess.
- Files written into `/music`; triggers Navidrome scan. Honors existing tag-reading and folder conventions. No new external dependency (raw Bot API via httpx, as today).
