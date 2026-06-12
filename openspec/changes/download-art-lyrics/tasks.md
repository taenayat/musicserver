## 1. YouTube cover art

- [x] 1.1 In `ytdlp.py:_download_sync`, add `"writethumbnail": True` and the `FFmpegMetadata` + `EmbedThumbnail` postprocessors to the options.
- [x] 1.2 Make thumbnail embedding best-effort so a missing thumbnail never fails the download.
- [ ] 1.3 Manually verify a downloaded YouTube file has embedded art.

## 2. Deezer cover art

- [x] 2.1 In `downloader.py:_configure`, set deemix artwork keys explicitly (`saveArtwork: true`, embedded artwork on).
- [ ] 2.2 Download a Deezer track and confirm embedded art (or folder `cover.jpg`) is present; expand config only if missing.

## 3. Cover-art backfill

- [x] 3.1 Add a `library.py` helper to detect whether a file has embedded art and whether its folder has a cover image.
- [x] 3.2 Add an embed helper (mutagen) to write a cover image into an audio file.
- [x] 3.3 Add an admin endpoint (e.g. `POST /api/admin/art/backfill`) that scans for tracks missing art, fetches Deezer cover when `deezer_id` known, embeds it, runs as a background task, and triggers a Navidrome scan.
- [x] 3.4 Reuse the existing trusted-cover-host check when fetching covers.
- [x] 3.5 Return/report the count of updated files.

## 4. Lyrics sidecars on download

- [x] 4.1 In `lyrics.py`, expose the raw synced LRC text (in addition to the parsed list) from the fetch path.
- [x] 4.2 Add a helper to write a `<basename>.lrc` sidecar next to an audio file.
- [x] 4.3 In `downloader.py:_finish_permanent`, after indexing each track, fetch lyrics and write a sidecar when synced LRC exists (non-blocking of the file landing).
- [x] 4.4 Confirm the existing post-download Navidrome scan picks up the sidecar.

## 5. Lyrics sidecar backfill

- [x] 5.1 Add an admin endpoint (e.g. `POST /api/admin/lyrics/backfill`) that walks `library_tracks`, skips files with an existing `.lrc`, fetches synced lyrics, writes sidecars, then triggers a scan.
- [x] 5.2 Return/report the count of sidecars written.

## 6. Frontend admin controls

- [x] 6.1 Add buttons in `pages/AdminPage.jsx` to trigger the cover-art backfill and the lyrics backfill, with toast feedback.
- [x] 6.2 Add the corresponding `api.js` methods.

## 7. Build & verify

- [x] 7.1 Rebuild frontend + gateway image.
- [ ] 7.2 Verify in Symfonium: a newly downloaded track shows art and (where available) lyrics; backfills populate existing tracks.
