## Why

Downloaded songs reach Symfonium without cover art (YouTube downloads never embed a thumbnail; deemix art needs verifying), and lyrics are only visible inside the gateway's own overlay — Navidrome and therefore Symfonium never see them. Both are about making downloaded files self-describing so the player the user actually listens in shows art and lyrics.

## What Changes

- **Embed cover art on every download** — add thumbnail embedding to the yt-dlp path (currently none) and verify/repair deemix artwork output so finished files carry embedded art. Provide an admin-triggered backfill that adds missing art to already-downloaded files.
- **Write lyrics as `.lrc` sidecars** — when synced lyrics are available (lrclib), write a `<track>.lrc` file next to the audio so Navidrome serves them to Symfonium. Generate at download time and via an admin-triggered backfill over the existing library. The gateway's in-app overlay continues to work unchanged.

## Capabilities

### New Capabilities
- `download-cover-art`: finished downloads carry embedded cover art (Deezer and YouTube paths), with a backfill for existing files missing art.
- `navidrome-lyrics-sidecar`: synced lyrics are written as `.lrc` sidecar files next to audio so Navidrome/Symfonium display them, generated on download and via backfill.

### Modified Capabilities
- None (no pre-existing specs).

## Impact

- Backend: `ytdlp.py` (EmbedThumbnail/FFmpegMetadata postprocessors), `downloader.py` (post-success art + lyrics sidecar hook), `lyrics.py` (helper to emit raw LRC + write sidecar), `main.py` (admin backfill endpoints + lyrics-on-download wiring), `library.py` (detect missing embedded art for backfill).
- New dependency: yt-dlp's thumbnail embedding needs `ffmpeg` (already in the image) and the `mutagen`/`Pillow` stack already present via mutagen; confirm no new pip deps beyond what exists.
- Files on disk: new `.lrc` sidecars in `/music`; embedded art written into audio files (deemix already, yt-dlp newly). Triggers a Navidrome scan after backfills.
