## Context

This is the interactive sibling of the cover-art backfill in the `download-art-lyrics` change. Where that backfill is a fire-and-forget "fix everything missing art" admin action, this tool adds a **review-and-select** workflow: scan → list with proposed covers → user picks → apply. Detection scope is **missing art only** (no "wrong art" heuristic), per decision — reliable and false-positive-free.

It operates over `library_tracks` (path, deezer_id, title/artist/album) and the files in `/music`. It reuses the Deezer client and the trusted-cover-host rules from `main.py`'s cover proxy.

## Goals / Non-Goals

**Goals:**
- Admin scan that lists tracks with no embedded art and no folder cover.
- Show each with a proposed Deezer cover (when a Deezer id is known).
- Per-track selection + select-all, then bulk apply (embed) + Navidrome scan.

**Non-Goals:**
- No "wrong art" / mismatch detection.
- No non-Deezer cover sources in v1 (tracks without a usable source are shown but not fixable).
- Not a background auto-fixer — this is explicitly user-driven (the auto/blind version is the backfill in change B).

## Decisions

**Share art helpers with change B.**
The cover-detection (`has_embedded_art` / folder-cover check) and the mutagen embed helper are the same primitives the `download-art-lyrics` backfill needs. If B lands first, reuse them; otherwise define them here in a small `artwork.py` and let B import them. Rationale: avoid duplicate art logic. Sequencing note: implement B's helpers first, or factor them here.

**Two endpoints: scan and apply.**
- `GET /api/admin/art/missing` → walks `library_tracks`, checks each file for embedded/folder art, returns the missing ones with `{track_id, title, artist, album, file_path, proposed_cover_url, fixable}`. `proposed_cover_url` is the Deezer cover for the track's `deezer_id` (or its album), `fixable=false` when none.
- `POST /api/admin/art/apply` with a list of track ids → for each, fetch the proposed cover (trusted host only), embed via mutagen, then trigger one Navidrome scan. Returns the updated count.
Rationale: clean separation of read (scan) and write (apply); apply takes an explicit id list so the UI fully controls scope.

**Cover source resolution.**
Prefer the track's Deezer album cover. For tracks indexed with `deezer_id` but no album cover cached, resolve via the Deezer client (`get_track` → album cover). Reuse the existing `_resize_cover`/host-allow-list logic. Rationale: consistent with the existing cover proxy and avoids untrusted fetches.

**Frontend: a dedicated admin screen.**
Add an "Album Art" tool (new tab or section in `AdminPage.jsx`) that calls the scan, renders a list of rows — current state (no art) vs proposed cover thumbnail, a checkbox per fixable row, a "Select all" toggle, and an "Apply to selected" button. After apply, refresh the list. Rationale: matches the user's described "scan → select → select-all → update" flow.

## Risks / Trade-offs

- **Scanning a large library reads every file's tags** → run the scan server-side, return a compact list; consider a soft cap / pagination if the library is huge. For v1, a single pass is acceptable; report progress via the existing scanning patterns if needed.
- **Embedding art rewrites audio files** → mutagen tag write only (not re-encode); low risk but back up via the existing Telegram path already covers many files. Apply is idempotent (re-running skips already-arted).
- **Deezer cover may differ from the "right" album art** for compilations → acceptable; detection is missing-only, and the user explicitly reviews/selects before applying.
- **Overlap with change B** → coordinate so art helpers live in one place; if B isn't done, this change defines them.

## Open Questions

- Pagination threshold for very large libraries — defer until a real library size is known; single pass for v1.
