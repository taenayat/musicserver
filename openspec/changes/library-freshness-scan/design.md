## Context

`navidrome.py:trigger_scan()` calls the Subsonic `startScan` view through `call()`, which catches every exception and returns `{}` (navidrome.py:158). So a failed scan is indistinguishable from a successful one, and `/api/admin/scan` always returns `{"status": "scan_triggered"}`. Navidrome also auto-scans every 1 minute (`ND_SCANSCHEDULE: 1m`) and exposes `getScanStatus` (already used by `server_stats()` for `scanning`/`last_scan`).

The deeper issue behind both #1 and #7 is architectural: Subsonic has no server push. The gateway can keep Navidrome current, but only Symfonium decides when to re-pull its library. The user accepted "new music appears" understanding it depends on Symfonium's own sync. So this change is about **observability + correct expectations**, not a new transport.

## Goals / Non-Goals

**Goals:**
- Make admin scan triggers report real success/failure.
- Show scan status (scanning, last scan) in the admin UI.
- Ensure all content-changing paths trigger an accepted scan and log failures.
- Document Symfonium background sync; set UI expectations.

**Non-Goals:**
- No attempt to push refreshes to Symfonium (impossible over Subsonic).
- No change to Navidrome's own scan schedule.
- No new persistence.

## Decisions

**Add a scan path that surfaces outcome.**
Add a `trigger_scan_checked()` (or make `trigger_scan` return a bool) that issues `startScan` without swallowing the result, returning whether Navidrome accepted it (HTTP ok + `subsonic-response.status == "ok"`). `/api/admin/scan` uses it and returns `{"ok": bool}`; background callers keep fire-and-forget semantics but log on failure. Rationale: minimal change, keeps existing silent `call()` for everything else.

**Expose scan status to the admin UI.**
`server_stats()` already returns `scanning` and `last_scan`; the admin status endpoint already surfaces `last_scan`. Add `scanning` to the admin status payload and render a "scanning…" indicator plus the existing last-scan time near the Trigger Scan button. Rationale: reuses data already fetched.

**Audit content-change scan calls.**
Confirm `trigger_scan()` is called after: permanent download (`_finish_permanent`), radio like, radio dismiss, recall, and the new backfills (cover/lyrics). Where it's fire-and-forget, log failures. Rationale: guarantees Navidrome learns of every change.

**Documentation + UI copy.**
Add a short section to `CONNECTING.md`/README on enabling Symfonium's background library sync (and a recommended interval), and add helper text by the scan controls clarifying the gateway-updates-Navidrome / client-refreshes-itself split. Rationale: sets correct expectations so "doesn't work in Symfonium" is understood as a client-sync cadence, not a broken trigger.

## Risks / Trade-offs

- **User may still perceive lag** until Symfonium next syncs → mitigated by documenting a short sync interval; nothing more is possible server-side.
- **`getScanStatus` shape differences across Navidrome versions** → already handled defensively in `server_stats()`; reuse it.
- **Changing `trigger_scan` return type** could affect callers → keep a non-breaking variant or update the few call sites together.

## Open Questions

- Whether to pass `fullScan=true` on the admin trigger. Default (incremental) should detect new files; leave incremental unless verification shows otherwise.
