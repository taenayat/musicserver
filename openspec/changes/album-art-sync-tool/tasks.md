## 1. Art helpers (backend)

- [x] 1.1 Ensure cover-detection helpers exist (embedded-art check + folder-cover check). Reuse from the download-art-lyrics change if present; otherwise define in a small `artwork.py`.
- [x] 1.2 Ensure a mutagen embed helper exists to write a cover image into an audio file.
- [x] 1.3 Add a cover-source resolver: given a library track, return the Deezer cover URL (track → album cover), reusing the trusted-host + resize logic.

## 2. Scan endpoint (backend)

- [x] 2.1 Add `GET /api/admin/art/missing` that walks `library_tracks`, checks each file for embedded/folder art, and returns missing-art tracks with `{track_id, title, artist, album, file_path, proposed_cover_url, fixable}`.
- [x] 2.2 Mark tracks with no usable cover source as `fixable: false`.

## 3. Apply endpoint (backend)

- [x] 3.1 Add `POST /api/admin/art/apply` taking a list of track ids; for each, fetch the proposed cover (trusted host only) and embed it.
- [x] 3.2 Skip un-fixable / already-arted tracks.
- [x] 3.3 Trigger a single Navidrome scan after applying and return the updated count.

## 4. Admin UI (frontend)

- [x] 4.1 Add `api.js` methods for the scan and apply endpoints.
- [x] 4.2 Add an "Album Art" tool to `pages/AdminPage.jsx` (new tab/section) that loads the missing-art list.
- [x] 4.3 Render each row: current "no art" state + proposed cover thumbnail, a checkbox for fixable rows, a "Select all" toggle, and "Apply to selected".
- [x] 4.4 After apply, show a toast with the count and refresh the list.

## 5. Build & verify

- [ ] 5.1 Rebuild frontend + gateway image.
- [ ] 5.2 Run the scan on a library with known art-less tracks; confirm they're listed with proposed covers.
- [ ] 5.3 Apply to a subset and to "select all"; confirm art embeds, the list shrinks, and Symfonium shows the new art after sync.
