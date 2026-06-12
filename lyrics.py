"""
lyrics.py — lyrics fetch with caching.

Source priority: lrclib.net (synced LRC) → Genius (plain, optional via
GENIUS_API_KEY). Results (including misses) are cached in lyrics_cache so we
don't re-hit the providers. Degrades gracefully: a null result means "no lyrics
found", never an error.
"""

import logging
import os
import re
from typing import Optional

log = logging.getLogger("lyrics")


def is_enabled() -> bool:
    return os.environ.get("LYRICS_ENABLED", "true").lower() in ("1", "true", "yes")


def parse_lrc(lrc_text: Optional[str]) -> list[dict]:
    """Parse `[MM:SS.ms] line` into [{time_ms, text}], sorted, skipping metadata."""
    if not lrc_text:
        return []
    out = []
    line_re = re.compile(r"((?:\[\d{1,2}:\d{2}(?:[.:]\d{1,3})?\])+)(.*)")
    ts_re = re.compile(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]")
    for raw in lrc_text.splitlines():
        m = line_re.match(raw.strip())
        if not m:
            continue
        text = m.group(2).strip()
        for ts in ts_re.finditer(m.group(1)):
            mm, ss, frac = ts.groups()
            ms = int(mm) * 60000 + int(ss) * 1000
            if frac:
                ms += int(frac.ljust(3, "0")[:3])
            out.append({"time_ms": ms, "text": text})
    out.sort(key=lambda x: x["time_ms"])
    return out


async def _fetch_lrclib(http, artist, title, album, duration_sec) -> Optional[dict]:
    params = {"artist_name": artist, "track_name": title}
    if album:
        params["album_name"] = album
    if duration_sec:
        params["duration"] = duration_sec
    for attempt_params in (params, {"artist_name": artist, "track_name": title}):
        try:
            r = await http.get("https://lrclib.net/api/get", params=attempt_params,
                               timeout=15.0)
            if r.status_code == 200:
                data = r.json()
                return {
                    "synced": data.get("syncedLyrics"),
                    "plain": data.get("plainLyrics"),
                }
            if r.status_code != 404:
                log.debug("lrclib status %s", r.status_code)
        except Exception as exc:
            log.debug("lrclib error: %s", exc)
        if attempt_params is params and not album:
            break  # no point retrying identical params
    return None


async def _fetch_genius(http, title, artist) -> Optional[str]:
    api_key = os.environ.get("GENIUS_API_KEY", "")
    if not api_key:
        return None
    try:
        r = await http.get("https://api.genius.com/search",
                           params={"q": f"{title} {artist}"},
                           headers={"Authorization": f"Bearer {api_key}"},
                           timeout=15.0)
        r.raise_for_status()
        hits = r.json().get("response", {}).get("hits", [])
        if not hits:
            return None
        url = hits[0]["result"]["url"]
        page = await http.get(url, timeout=15.0)
        page.raise_for_status()
        html = page.text
        blocks = re.findall(
            r'<div[^>]*data-lyrics-container[^>]*>(.*?)</div>', html, re.DOTALL)
        if not blocks:
            return None
        text = "\n".join(blocks)
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text or None
    except Exception as exc:
        log.debug("genius error: %s", exc)
        return None


def lrc_sidecar_path(audio_abs_path: str) -> str:
    """The .lrc sidecar path for an audio file (same basename)."""
    return os.path.splitext(audio_abs_path)[0] + ".lrc"


def write_lrc_sidecar(audio_abs_path: str, lrc_text: str) -> bool:
    """Write synced LRC text next to the audio file. Non-destructive."""
    if not lrc_text:
        return False
    path = lrc_sidecar_path(audio_abs_path)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(lrc_text)
        return True
    except OSError as exc:
        log.warning("write lrc sidecar failed for %s: %s", path, exc)
        return False


async def get_sidecar_lrc(http, db, deezer_track_id: int, title: str, artist: str,
                          album: Optional[str], duration_sec: Optional[int]
                          ) -> Optional[str]:
    """Return the best LRC text to write as a .lrc sidecar, or None.

    Prefers synced (timestamped) lyrics; falls back to plain (unsynced) text —
    Navidrome serves a no-timestamp .lrc as unsynced lyrics, which Symfonium
    still shows, so plain is better than nothing (e.g. for Persian tracks where
    lrclib only has plain). Uses the lyrics_cache when present, else hits lrclib.
    """
    if deezer_track_id:
        cached = await db.get_lyrics(deezer_track_id)
        if cached:
            return cached.get("synced") or cached.get("plain")

    lrc = await _fetch_lrclib(http, artist, title, album, duration_sec)
    synced = lrc.get("synced") if lrc else None
    plain = lrc.get("plain") if lrc else None
    if deezer_track_id and (synced or plain):
        await db.upsert_lyrics(deezer_track_id, synced, plain, "lrclib")
    return synced or plain


async def fetch_lyrics(http, db, deezer_track_id: int, title: str, artist: str,
                       album: Optional[str], duration_sec: Optional[int]) -> dict:
    if deezer_track_id:
        cached = await db.get_lyrics(deezer_track_id)
        if cached:
            return {"synced": parse_lrc(cached.get("synced")),
                    "plain": cached.get("plain"),
                    "source": cached.get("source")}

    synced = plain = source = None
    lrc = await _fetch_lrclib(http, artist, title, album, duration_sec)
    if lrc and (lrc.get("synced") or lrc.get("plain")):
        synced = lrc.get("synced")
        plain = lrc.get("plain")
        source = "lrclib"
    else:
        g = await _fetch_genius(http, title, artist)
        if g:
            plain = g
            source = "genius"

    if deezer_track_id:
        await db.upsert_lyrics(deezer_track_id, synced, plain, source)

    return {"synced": parse_lrc(synced), "plain": plain, "source": source}
