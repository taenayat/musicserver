## Why

Today Telegram is treated as a one-way cold-storage *backup* of the SSD library, and the inbound bot-API path can't reliably ingest (no `channel_post` delivery + a 20 MB `getFile` cap). The user wants the relationship inverted: **Telegram is the source of truth**, the SSD (`/music`) is a working/hot copy. Adding a track to the channel should surface it in Navidrome; removing a track from the channel should (safely, with admin confirmation) remove it from the SSD. The admin needs visibility into drift between the two stores.

## What Changes

- **Switch Telegram access from the Bot API to an MTProto user session** (Telethon-based), removing the 20 MB download cap and giving full channel history + reliable message listing. The existing bot stays only for what it already does well (outbound upload notifications) or is retired in favor of MTProto.
- **Reconcile SSD ↔ Telegram** on a schedule and on demand:
  - **Additions (Telegram → SSD):** audio present in the channel but missing from the SSD/library is retrieved into `/music`, indexed, and a Navidrome scan is triggered. These are applied automatically and are **not** surfaced as discrepancies.
  - **Deletions (Telegram → SSD):** audio present on the SSD/library but **not** in the channel is surfaced in an admin "discrepancies" view. The admin selects which to remove (or select-all) and the gateway deletes them from the SSD. Destructive removal is **never** automatic.
- **tgmount option for hot-cache + recall:** optionally mount the channel as a FUSE filesystem so evicted hot-cache files can be re-read/recalled from Telegram without the bot-API size limit, and so directory diffing makes drift detection trivial. (Design weighs tgmount/FUSE vs a pure-Telethon reconciler — see design.md.)
- **Admin "Telegram" tab gains a discrepancy/reconcile panel:** run reconcile, show SSD-only tracks (candidates for deletion), select + remove, and show last-reconcile status.

## Capabilities

### New Capabilities
- `telegram-mtproto-access`: the gateway talks to Telegram via an MTProto user session (full history, no 20 MB cap) for listing, downloading, and detecting deletions.
- `telegram-reconcile`: scheduled/on-demand reconciliation that imports channel additions into the SSD and detects SSD-only tracks as deletion candidates, treating Telegram as canonical.
- `telegram-discrepancy-admin`: an admin panel that surfaces SSD-vs-Telegram drift and lets the admin remove SSD-only tracks (individually or all).

### Modified Capabilities
- None. (The `telegram-inbound-ingest` change is not yet archived into main specs, so there is no delta to write; this change supersedes its bot-API inbound path — tracked in Impact below and reconciled when that change is archived.)

## Impact

- **New dependency:** Telethon (MTProto). Requires `TELEGRAM_API_ID` + `TELEGRAM_API_HASH` (from my.telegram.org) and a generated **user session string**. New env vars + first-run/session-setup step.
- **Operational (if tgmount/FUSE chosen):** the gateway container needs `/dev/fuse` + `SYS_ADMIN` cap (or `--privileged`); docker-compose changes. The pure-Telethon reconciler avoids this.
- **Code:** new `tg_mtproto.py` (Telethon client + list/download/watch-deletions), `reconcile.py` (diff + apply), `main.py` (admin reconcile/discrepancy endpoints + lifespan wiring), `db.py` (track Telegram message↔file mapping is already partly present via `telegram_files`), frontend `AdminPage.jsx` Telegram tab.
- **Safety:** deletion propagation is admin-gated; reconciliation must never delete based on a transient/empty channel listing (guard against an empty or failed fetch wiping the library).
- **Supersedes** the `telegram-inbound-ingest` bot path.
