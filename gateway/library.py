"""
library.py — local music library index + "already in library" matching.

Walks /music/ (excluding /music/radio/), reads tags with mutagen, and upserts a
row per file into library_tracks. The index powers two things:
  • search enrichment ("✓ In Library" badges) and the download gate, via
    is_in_library(), which matches on Deezer id first, then a normalised
    title+artist fingerprint (with a duration sanity check).
  • cache eviction accounting (file sizes / locations).

mutagen and os.walk are synchronous, so the scan body runs in asyncio.to_thread.
"""

import asyncio
import logging
import os
import re
from typing import Optional

log = logging.getLogger("library")

AUDIO_EXTS = (".mp3", ".flac", ".aac", ".m4a", ".ogg", ".opus")

_NOISE_TOKENS = [
    "remastered", "explicit", "radio edit", "deluxe", "feat", "ft",
    "featuring", "bonus track", "live", "version", "edition",
]


def compute_fingerprint(title: str, artist: str) -> str:
    combined = f"{(title or '').lower()} {(artist or '').lower()}"
    result = re.sub(r"[^\w\s]", "", combined)
    for t in _NOISE_TOKENS:
        result = result.replace(t, "")
    return re.sub(r"\s+", " ", result).strip()


# ── tag reading (sync — call inside to_thread) ──────────────────────────────

def _read_tags(abs_path: str, rel_path: str) -> dict:
    from mutagen import File as MutagenFile

    title = artist = album = None
    track_number = duration = bitrate = None
    fmt = os.path.splitext(abs_path)[1].lstrip(".").lower()

    try:
        mf = MutagenFile(abs_path, easy=True)
        if mf is not None:
            tags = mf.tags or {}

            def first(key):
                v = tags.get(key)
                if isinstance(v, list):
                    return v[0] if v else None
                return v

            title = first("title")
            artist = first("artist")
            album = first("album")
            tn = first("tracknumber")
            if tn:
                m = re.match(r"\d+", str(tn))
                track_number = int(m.group()) if m else None
            info = getattr(mf, "info", None)
            if info is not None:
                duration = int(getattr(info, "length", 0) or 0) or None
                br = getattr(info, "bitrate", None)
                if br:
                    bitrate = int(br / 1000)
    except Exception as exc:
        log.warning("tag read failed for %s: %s", rel_path, exc)

    # Derive from path when tags are missing: <Artist>/<Album>/<NN_Title.ext>
    parts = rel_path.split(os.sep)
    if not title:
        base = os.path.splitext(parts[-1])[0]
        title = re.sub(r"^\d+[_\-\.\s]+", "", base) or base
    if not artist:
        artist = parts[0] if len(parts) >= 2 else "Unknown Artist"
    if not album and len(parts) >= 3:
        album = parts[-2]

    try:
        size_mb = round(os.path.getsize(abs_path) / 1e6, 3)
    except OSError:
        size_mb = None

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "track_number": track_number,
        "duration_sec": duration,
        "file_size_mb": size_mb,
        "format": fmt,
        "bitrate_kbps": bitrate,
        "fingerprint": compute_fingerprint(title, artist),
    }


def _walk_audio(music_dir: str) -> list[tuple[str, str]]:
    found = []
    radio_root = os.path.join(music_dir, "radio")
    for root, dirs, files in os.walk(music_dir):
        if root == radio_root or root.startswith(radio_root + os.sep):
            continue
        for name in files:
            if name.lower().endswith(AUDIO_EXTS):
                abs_path = os.path.join(root, name)
                rel_path = os.path.relpath(abs_path, music_dir)
                found.append((abs_path, rel_path))
    return found


# ── scan ────────────────────────────────────────────────────────────────────

async def scan_library(music_dir: str, db) -> dict:
    files = await asyncio.to_thread(_walk_audio, music_dir)
    scanned = added = updated = 0
    for abs_path, rel_path in files:
        existing = await db.get_library_track_by_path(rel_path)
        tags = await asyncio.to_thread(_read_tags, abs_path, rel_path)
        await db.upsert_library_track(
            file_path=rel_path,
            location=(existing or {}).get("location", "local"),
            **tags,
        )
        scanned += 1
        if existing:
            updated += 1
        else:
            added += 1
    log.info("library scan: %d scanned (%d new, %d updated)", scanned, added, updated)
    return {"scanned": scanned, "added": added, "updated": updated}


# ── "already in library" ─────────────────────────────────────────────────────

async def is_in_library(deezer_track: dict, db) -> Optional[dict]:
    """Return the matching library_tracks row, or None."""
    dz_id = deezer_track.get("id")
    if dz_id:
        row = await db.get_library_track_by_deezer_id(dz_id)
        if row:
            return row

    title = deezer_track.get("title") or ""
    artist = deezer_track.get("artist_name") or (
        deezer_track.get("artist", {}).get("name") if isinstance(deezer_track.get("artist"), dict) else ""
    ) or ""
    if not title:
        return None

    fp = compute_fingerprint(title, artist)
    row = await db.get_library_track_by_fingerprint(fp)
    if not row:
        return None

    dz_duration = deezer_track.get("duration")
    if dz_duration and row.get("duration_sec"):
        if abs(row["duration_sec"] - dz_duration) > 10:
            return None  # likely a different recording

    # Back-fill deezer_id on an exact normalized title+artist match.
    if row.get("deezer_id") is None and dz_id:
        if compute_fingerprint(row["title"], row["artist"]) == fp:
            await db.backfill_deezer_id(
                row["file_path"], dz_id, deezer_track.get("album_id")
            )
            row["deezer_id"] = dz_id
    return row


async def enrich_with_library(tracks: list[dict], db) -> list[dict]:
    """Add in_library / library_path / library_format to each track dict."""
    for t in tracks:
        row = await is_in_library(t, db)
        if row:
            t["in_library"] = True
            t["library_path"] = row["file_path"]
            t["library_format"] = row.get("format")
            t["library_bitrate_kbps"] = row.get("bitrate_kbps")
        else:
            t["in_library"] = False
            t["library_path"] = None
            t["library_format"] = None
    return tracks
