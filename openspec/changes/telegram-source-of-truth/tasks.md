## 1. MTProto access

- [ ] 1.1 Add Telethon to requirements; add `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` env + docs (my.telegram.org).
- [ ] 1.2 Add a one-time interactive helper to mint and store a user session string under `/data` (never logged/committed).
- [ ] 1.3 Create `tg_mtproto.py`: connect with the session; `list_channel_audio()` returning `{msg_id, file_unique_id, performer, title, file_name, size}` per audio message.
- [ ] 1.4 Add `download(msg_or_id, dest)` (no size cap) and a "which of these msg_ids still exist" check for deletion detection.
- [ ] 1.5 Fail closed (feature disabled, clear log) when credentials/session are missing; never emit the session string.

## 2. Identity & schema

- [ ] 2.1 Store Telegram `file_unique_id` alongside `msg_id` in `telegram_files` (migration).
- [ ] 2.2 Implement matching: recorded id → fingerprint+duration → filename.

## 3. Reconciler (report-only first)

- [ ] 3.1 Create `reconcile.py`: list channel audio, diff against library/SSD, compute additions + SSD-only deletion candidates.
- [ ] 3.2 Guard: abort (no candidates) on empty/failed channel listing.
- [ ] 3.3 Restrict deletion candidates to telegram-backed/sourced tracks only.
- [ ] 3.4 Report-only mode: produce counts/lists, apply nothing.

## 4. Apply additions

- [ ] 4.1 Download channel additions into `/music/<Artist>/<Album>/`, index, mark telegram-backed.
- [ ] 4.2 Trigger a single Navidrome scan after a batch of additions.

## 5. Admin discrepancy panel + gated deletion

- [ ] 5.1 Endpoints: `POST /api/admin/telegram/reconcile` (run + return additions summary and SSD-only candidates), `POST /api/admin/telegram/remove` (delete selected SSD-only tracks + scan).
- [ ] 5.2 Frontend: Telegram tab panel — run reconcile, list candidates with metadata, per-row checkbox + select-all, remove action, last-run status.
- [ ] 5.3 Ensure removal deletes files + library rows and never runs without explicit admin action.

## 6. Hot-cache recall via MTProto

- [ ] 6.1 Point cache recall at MTProto download (remove the 20 MB bot-API ceiling); keep eviction unchanged.

## 7. Optional: tgmount (FUSE) — only if a privileged container is acceptable

- [ ] 7.1 Decide with the user whether `/dev/fuse` + `SYS_ADMIN` is acceptable.
- [ ] 7.2 If yes: mount the channel and use it for recall/streaming + directory-diff drift detection.

## 8. Retire bot inbound

- [ ] 8.1 Remove or disable the bot-API `getUpdates` inbound worker once reconciliation is verified.

## 9. Verify

- [ ] 9.1 Add a track to the channel → reconcile imports it → appears in Symfonium.
- [ ] 9.2 Remove a track from the channel → it appears as an SSD-only candidate → admin removes it → gone from SSD + Navidrome.
- [ ] 9.3 Simulate a failed/empty listing → confirm no deletion candidates are produced.
- [ ] 9.4 Recall a >20 MB evicted file from Telegram successfully.
