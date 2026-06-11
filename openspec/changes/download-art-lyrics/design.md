## Context

Downloads land via two paths: deemix (`downloader.py:_run_deemix`) and yt-dlp (`ytdlp.py:_download_sync`). After a permanent success, `_finish_permanent` indexes the files, triggers a Navidrome scan, and enqueues a Telegram backup. Lyrics are fetched on demand by `lyrics.py:fetch_lyrics` (lrclib → Genius) and rendered only in the gateway's `LyricsOverlay`; lrclib returns raw synced LRC text (`syncedLyrics`).

Navidrome displays art from embedded tags or folder images (`cover.*`/`folder.*`/`front.*`) and lyrics from embedded tags or `.lrc` sidecars. So making downloads self-describing on disk is what surfaces art/lyrics in Symfonium.

## Goals / Non-Goals

**Goals:**
- Embedded cover art on both download paths; backfill for existing files.
- `.lrc` sidecars for synced lyrics, on download and via backfill.

**Non-Goals:**
- No embedding of lyrics into audio tags (sidecar chosen — non-destructive). 
- No change to the gateway's in-app lyrics overlay behavior.
- No "wrong art" detection here (that's the album-art-sync-tool change); this change only fixes missing art on downloads + a simple backfill.

## Decisions

**yt-dlp: embed thumbnail via postprocessors.**
Add `{"key": "FFmpegMetadata"}` and `{"key": "EmbedThumbnail"}` to the yt-dlp options, plus `"writethumbnail": True`. ffmpeg is already in the image. Rationale: standard, reliable yt-dlp mechanism; no manual mutagen work for the YouTube path.

**deemix: verify, then make artwork explicit.**
deemix defaults embed art, but the config is set narrowly. Set `saveArtwork: true` (folder `cover.jpg`) and `embeddedArtwork`/`saveArtworkArtist` as needed in `_configure`, so behavior is explicit rather than relying on defaults. Verify against a real download during implementation; only expand if art is actually missing. Rationale: smallest change that guarantees art without guessing.

**Cover-art backfill: detect missing, embed via mutagen.**
Add a library helper that reports whether a file has embedded art (mutagen: presence of `APIC`/`covr`/picture) and whether its folder has a cover image. For files missing both, fetch a cover — Deezer canonical cover when `deezer_id` is known (reuse the existing cover proxy/host rules), else skip — and embed it with mutagen. Run as a background task behind a new admin endpoint, then trigger a Navidrome scan. Rationale: reuses mutagen already used for tag reading; isolates the heavy work behind an admin action.

**Lyrics sidecar: emit raw LRC, write next to file.**
Add a `lyrics.py` helper that returns the raw synced LRC string (today `fetch_lyrics` parses it into a list; keep the raw text available). In `_finish_permanent`, after indexing, fetch lyrics for the track and, if `synced` raw LRC exists, write `<basename>.lrc` beside the audio. Add an admin backfill endpoint that walks `library_tracks`, skips files with an existing sidecar, fetches synced lyrics, writes sidecars, then triggers a scan. Rationale: sidecar is non-destructive, trivially regenerable, and natively understood by Navidrome.

**Scan batching.**
Download-time sidecar/art writes happen before the existing `_finish_permanent` scan trigger, so they ride the same scan. Backfills trigger one scan at the end, not per file.

## Risks / Trade-offs

- **Lyrics fetch at download time adds latency / external calls** → fetch is already cached in `lyrics_cache`; do it after status is marked done so it never blocks the file landing.
- **EmbedThumbnail can fail for some formats** → wrap in best-effort; a missing thumbnail must not fail the download.
- **Backfills are I/O heavy over a large library** → run as background tasks, single trailing scan, report counts; safe to re-run (idempotent: skip files already arted/sidecar'd).
- **Deezer cover host allow-list** → reuse existing `_cover_allowed` logic so backfill only pulls from trusted hosts.

## Open Questions

- For files with no Deezer id and no embeddable source, cover backfill simply skips them — acceptable for v1.
