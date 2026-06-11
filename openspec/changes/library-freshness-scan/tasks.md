## 1. Scan trigger reports outcome (backend)

- [x] 1.1 In `navidrome.py`, add a scan path that issues `startScan` and returns whether Navidrome accepted it (HTTP ok + `status == "ok"`), without swallowing the result.
- [x] 1.2 Update `/api/admin/scan` in `main.py` to use it and return a real `{"ok": bool}` (or error detail on failure).
- [x] 1.3 Keep background callers fire-and-forget but log a warning when the scan call fails.

## 2. Expose scan status (backend)

- [x] 2.1 Ensure the admin status payload includes Navidrome `scanning` (already has `last_scan`).
- [x] 2.2 Confirm `server_stats()`/`getScanStatus` values are passed through.

## 3. Audit content-change scans (backend)

- [x] 3.1 Verify `trigger_scan()` is called after: permanent download, radio like, radio dismiss, recall, and the cover/lyrics backfills.
- [x] 3.2 Add failure logging where scans are fire-and-forget.

## 4. Admin UI feedback (frontend)

- [x] 4.1 In `pages/AdminPage.jsx`, make the Trigger Scan button reflect the real success/failure outcome via toast.
- [x] 4.2 Show a "scanning…" indicator when Navidrome is mid-scan and the last-scan time near the control.
- [x] 4.3 Add helper text clarifying gateway-updates-Navidrome vs Symfonium-refreshes-on-its-own-schedule.

## 5. Documentation

- [x] 5.1 Add a section to `CONNECTING.md`/README on enabling Symfonium background library sync and a recommended interval so new music appears automatically.

## 6. Verify

- [ ] 6.1 Trigger a scan with Navidrome up: UI confirms success and shows scanning/last-scan.
- [ ] 6.2 Trigger a scan with Navidrome unreachable: UI reports failure.
- [ ] 6.3 With Symfonium background sync enabled, confirm a new download appears without manual refresh within the sync window.
