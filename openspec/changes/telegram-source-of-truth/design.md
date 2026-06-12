## Context

The current Telegram integration (`telegram.py`) uses the **Bot API**: outbound `sendAudio` for backup, and an inbound `getUpdates` poll added recently. Live debugging confirmed two hard limits of that path:
- The bot, though a channel **administrator**, receives **no `channel_post` updates** for forwarded/posted audio — so inbound ingest never fires.
- Bot API `getFile` caps downloads at ~20 MB, too small for many tracks.

These make the Bot API unsuitable for "Telegram as source of truth." MTProto (a **user** session, via Telethon) has neither limit: it can list a channel's full message history, download arbitrarily large files, and observe deletions. The user explicitly suggested **tgmount** (a FUSE filesystem over a Telegram chat, built on Telethon) as the mechanism.

Existing building blocks we keep: the `telegram_files` table (rel_path ↔ msg_id/file_id), `library_tracks` (with `telegram_backed`, `location`), `is_in_library` dedupe, `_read_tags`, and the Navidrome scan trigger.

## Goals / Non-Goals

**Goals:**
- Treat the Telegram channel as canonical: additions flow in automatically; deletions are detected and applied to the SSD under admin control.
- Remove the 20 MB cap and the channel-post delivery problem via MTProto.
- Give the admin a clear discrepancy view (SSD-only tracks) with select/select-all removal.
- Make hot-cache recall work for any file size.

**Non-Goals:**
- Automatic, unattended deletion of SSD files (too dangerous — always admin-gated).
- Replacing Navidrome's scanning model.
- Migrating already-backed files; the reconciler converges the two stores over time.

## Decisions

### D1. MTProto user session (Telethon), not the bot, for the source-of-truth path
Add `tg_mtproto.py` wrapping Telethon with `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` and a stored **session string**. Capabilities: `list_channel_audio()` (iterate messages with audio, returning msg_id, file ref, performer/title/filename/size/unique_id), `download(msg, dest)`, and `resolve_deletions(known_msg_ids)` (which known message ids no longer exist).
- *Why:* only MTProto removes both limits and can detect deletions. The bot session can stay for outbound notifications or be retired.
- *Alternative:* stay on Bot API — rejected (proven insufficient).
- *Session setup:* one-time, interactive (phone + code) to mint a session string stored in `/data`. Document a `make`/CLI helper; never commit the string. New first-run/admin step.

### D2. Reconciler approach — pure-Telethon diff first, tgmount as an optional layer
Two ways to "see" the channel:
- **(A) Pure Telethon reconciler:** list channel audio via MTProto, build a set keyed by a stable id (Telegram file `unique_id` or a content hash), diff against `library_tracks`/`telegram_files`. Apply additions (download missing) and flag SSD-only as deletion candidates. No FUSE.
- **(B) tgmount FUSE mount:** mount the channel at e.g. `/tg`, and diff directories / read files directly. Elegant for recall (reading a file streams from TG) and for "what's deleted" (it's just not in the mount). Needs `/dev/fuse` + `SYS_ADMIN` (or privileged) in docker-compose.

**Recommendation:** ship **(A) the pure-Telethon reconciler** as the core — it needs no privileged container, is easier to reason about for the destructive deletion path, and fully delivers additions + discrepancy detection. Offer **(B) tgmount** as an optional enhancement for hot-cache recall/streaming where FUSE is acceptable. This keeps the safety-critical logic in plain code and treats tgmount as a convenience, not a dependency.
- *Open question for the user:* is running the gateway container with FUSE/SYS_ADMIN acceptable? If not, we do (A) only.

### D3. Stable identity for matching SSD ↔ Telegram
Match on, in order: (1) recorded `telegram_files.msg_id`/`file_unique_id` ↔ live message ids; (2) the existing title+artist fingerprint + duration; (3) filename. Store Telegram `file_unique_id` alongside `msg_id` so re-runs are stable even if message ids are re-fetched.
- *Why:* `unique_id` is stable per file across the account; fingerprint covers files imported before we recorded ids.

### D4. Additions are automatic; deletions are admin-gated
- **Additions:** during reconcile, any channel audio with no matching SSD/library row is downloaded into `/music/<Artist>/<Album>/`, indexed, marked `telegram_backed`, and a single Navidrome scan is triggered at the end. Not shown as a discrepancy.
- **Deletions:** any `library_tracks` row whose backing message is gone from the channel (and which is recorded as telegram-sourced/backed) becomes a **deletion candidate**. The admin sees these in the Telegram tab and removes them explicitly. Never auto-deleted.
- *Why:* matches the user's "don't show additions, show SSD-only for removal" and keeps destruction human-approved.

### D5. Deletion-safety guards
- Never compute deletion candidates from an **empty or failed** channel listing (a fetch error or transient empty result must abort reconcile, not flag everything for deletion).
- Only files recorded as telegram-backed/sourced are eligible as deletion candidates — locally-managed-only files (never in TG) are out of scope of source-of-truth removal unless the user opts in.
- Require a minimum sane channel size / explicit confirm before listing large deletion sets.
- *Why:* the failure mode here is wiping the library; guard aggressively.

### D6. Hot-cache recall via MTProto (supersedes bot recall)
Replace the bot-API recall (`cache.recall_track`) source with MTProto download (or a tgmount read), removing the 20 MB ceiling. Eviction stays as-is; recall just gets a bigger, reliable backend.

## Risks / Trade-offs

- **Destructive deletion path** → admin-gated + empty-listing guard + telegram-backed-only eligibility (D4/D5).
- **MTProto session security** (a user session string is powerful) → store in `/data` with tight perms, never log, document rotation. [Risk] leaked session → full account access → keep out of git/logs.
- **Telethon flood-wait / rate limits** on large channels → paginate, back off, cache the listing between runs.
- **FUSE-in-docker operational cost** (if D2-B) → made optional; core works without it.
- **Identity drift** (same song, different file) → multi-key matching (D3) + admin review before deletion.

## Migration Plan

1. Add Telethon + env (`TELEGRAM_API_ID/HASH`), mint a session string (one-time interactive helper), store in `/data`.
2. Ship the reconciler in **report-only** mode first: it lists additions/deletions but applies nothing; admin reviews in the new tab.
3. Enable automatic additions once verified.
4. Enable admin-gated deletions.
5. (Optional) add tgmount for recall/streaming if FUSE is acceptable.
6. Retire the bot-API `getUpdates` inbound worker.

## Open Questions

- Is a privileged/FUSE-capable gateway container acceptable (decides tgmount vs pure-Telethon-only)?
- Keep the backup bot for outbound notifications, or move everything to MTProto?
- Should locally-managed-only files (never in TG) ever be auto-uploaded to TG to "join" the source of truth, or stay local? (Leaning: offer an admin "push to Telegram" action, not automatic.)
