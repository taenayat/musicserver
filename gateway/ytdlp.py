"""
ytdlp.py — YouTube Music search + download via the yt_dlp Python API.

USER-TRIGGERED ONLY. The gateway never calls YouTube automatically; the user
explicitly clicks the YouTube search button. Both search and download run the
synchronous yt_dlp API inside asyncio.to_thread so the event loop is never
blocked.

Enabled by YTDLP_ENABLED=true. When false the search route returns 503.
"""

import asyncio
import logging
import os
import re
from typing import Optional

log = logging.getLogger("ytdlp")


def is_enabled() -> bool:
    return os.environ.get("YTDLP_ENABLED", "true").lower() in ("1", "true", "yes")


def _search_sync(query: str, limit: int) -> list[dict]:
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "default_search": f"ytsearch{limit}:",
        "skip_download": True,
    }
    results = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(query, download=False)
        for e in (info or {}).get("entries", []) or []:
            if not e:
                continue
            results.append({
                "yt_id": e.get("id"),
                "title": e.get("title", ""),
                "artist": e.get("uploader") or e.get("channel") or "",
                "duration": int(e.get("duration") or 0),
                "thumbnail_url": _best_thumb(e),
                "source": "youtube",
            })
    return results


def _best_thumb(entry: dict) -> str:
    thumbs = entry.get("thumbnails") or []
    if thumbs:
        return thumbs[-1].get("url", "")
    return entry.get("thumbnail", "") or ""


async def search_youtube_music(query: str, limit: int = 10) -> list[dict]:
    if not query.strip():
        return []
    try:
        return await asyncio.to_thread(_search_sync, query, limit)
    except Exception as exc:
        log.error("yt-dlp search failed for %r: %s", query, exc)
        return []


def _sanitize(name: str) -> str:
    name = (name or "").strip() or "Unknown"
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def _download_sync(yt_id: str, dest_dir: str, artist: str, album: str) -> str:
    import yt_dlp

    artist_s = _sanitize(artist)
    album_s = _sanitize(album or "Singles")
    out_dir = os.path.join(dest_dir, artist_s, album_s)
    os.makedirs(out_dir, exist_ok=True)

    captured = {"path": None}

    def hook(d):
        if d.get("status") == "finished":
            captured["path"] = d.get("filename")

    opts = {
        "format": "bestaudio/best",
        # Fetch the thumbnail and embed it so Navidrome/Symfonium show cover art.
        # EmbedThumbnail is best-effort: a missing/unembeddable thumbnail only
        # warns, it never fails the download.
        "writethumbnail": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            },
            {"key": "FFmpegMetadata"},
            {"key": "EmbedThumbnail"},
        ],
        "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={yt_id}"])

    # The progress hook captures the pre-postprocessing name; swap to .mp3.
    path = captured["path"]
    if path:
        mp3 = os.path.splitext(path)[0] + ".mp3"
        if os.path.isfile(mp3):
            return mp3
        if os.path.isfile(path):
            return path
    # Fallback: newest mp3 in the output dir.
    mp3s = [os.path.join(out_dir, f) for f in os.listdir(out_dir)
            if f.lower().endswith(".mp3")]
    if mp3s:
        return max(mp3s, key=os.path.getmtime)
    raise RuntimeError("yt-dlp produced no output file")


async def download_track(yt_id: str, dest_dir: str, artist: str,
                         album: Optional[str] = None) -> str:
    return await asyncio.to_thread(_download_sync, yt_id, dest_dir, artist, album or "Singles")
