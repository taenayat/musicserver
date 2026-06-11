## Why

The library accumulates tracks with no cover art (older downloads, imports, files that slipped through). There's no way to find and fix them in bulk. Users want to scan the library, see which tracks are missing art, and fix some or all of them from one screen — without hunting file by file.

## What Changes

- **Add an album-art sync tool** — an admin scan that finds library tracks lacking cover art (no embedded image and no folder cover), lists them with the proposed replacement cover, and lets the admin select individual tracks or "select all" and apply art to the chosen ones in one action.
- Scope of detection is **missing art only** (not "wrong" art), per decision — reliable and unambiguous.
- Replacement cover comes from Deezer (canonical cover for tracks with a known Deezer id); tracks with no available cover source are shown as un-fixable and excluded from "apply".
- Applying art embeds the image and triggers a Navidrome scan so Symfonium reflects it.

## Capabilities

### New Capabilities
- `album-art-sync`: scan the library for tracks missing cover art, review candidates with proposed covers, select individually or all, and apply embedded art in bulk.

### Modified Capabilities
- None (no pre-existing specs).

## Impact

- Backend: new endpoints to scan for missing-art tracks and to apply art to a selected set (reuses the cover-detection + embed helpers introduced for the download-art-lyrics backfill, if present; otherwise defines them here). `main.py`, `library.py`, possibly a small `artwork.py` helper module.
- Frontend: a new admin screen/tab listing missing-art tracks with thumbnails, checkboxes, a select-all control, and an apply button. `pages/AdminPage.jsx` (+ new component), `api.js`.
- Reuses the existing trusted-cover-host proxy rules and Deezer client. Triggers a Navidrome scan after applying. No schema changes (operates on files + `library_tracks`).
