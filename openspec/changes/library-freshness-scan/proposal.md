## Why

The admin "Trigger Scan" button appears to do nothing in Symfonium, and freshly downloaded music doesn't show up without a manual pull-to-refresh. The gateway already asks Navidrome to rescan, but failures are swallowed silently and there's no feedback that a scan ran — and crucially, Subsonic has no way to push a refresh to Symfonium, so expectations need to be set correctly. This change makes scan triggers observable and reliable, and documents the one client-side setting that makes new music "just appear."

## What Changes

- **Surface scan success/failure** — the Navidrome scan call currently swallows all errors and returns `{}`. Make admin-triggered scans report whether Navidrome accepted the scan, and show scan status (scanning / last scan time) in the admin UI so "did it work?" is answerable.
- **Confirm post-content scans fire reliably** — audit the existing `trigger_scan()` calls after downloads, radio like/dismiss, and backfills so a content change always results in an accepted scan.
- **Document Symfonium freshness** — because the gateway cannot push to Symfonium, document the Symfonium background-sync setting (and recommended interval) so newly downloaded music appears without manual refresh, and reflect this expectation in the admin UI copy.

## Capabilities

### New Capabilities
- `navidrome-scan-feedback`: admin scan triggers report acceptance/failure and expose Navidrome scan status to the UI.
- `library-freshness`: content changes reliably trigger an accepted Navidrome scan, and Symfonium client-sync guidance is documented so new music surfaces without manual refresh.

### Modified Capabilities
- None (no pre-existing specs).

## Impact

- Backend: `navidrome.py` (a scan path that surfaces success/failure instead of swallowing; expose `getScanStatus`), `main.py` (`/api/admin/scan` returns real outcome; admin status already includes `last_scan`/`scanning`).
- Frontend: `pages/AdminPage.jsx` (show scan accepted/failed toast + scanning indicator + last-scan time).
- Docs: `CONNECTING.md`/README note on Symfonium background sync; admin UI helper text.
- No schema changes.
