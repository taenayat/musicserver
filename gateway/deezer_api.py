"""
deezer_api.py — thin async client over api.deezer.com.

(Formerly deezer.py. Renamed so it can no longer shadow the `deezer-py`
package that deemix imports as `deezer`. The old deezer.py MUST be deleted.)

All endpoints used here are public and unauthenticated. The ARL is only
needed at download time (handled in downloader.py).

Resilience added on top of the original thin client:
  • In-memory TTL response cache — repeated lookups for the same artist/
    album/track (Symfonium re-fetches a lot) cost zero API calls.
  • A concurrency semaphore caps simultaneous requests so a burst can't
    trip Deezer's per-window quota.
  • One automatic retry with back-off when Deezer answers HTTP 200 with
    its quota error (error code 4) — that's how rate-limiting shows up,
    and the original code silently turned it into empty results.
"""

import asyncio
import logging
import time
from typing import Optional

import httpx

log = logging.getLogger("deezer")

_CACHE_TTL      = 300      # seconds to keep a successful response
_CACHE_MAX      = 5000     # soft cap on cache entries
_MAX_CONCURRENCY = 6       # simultaneous in-flight Deezer requests
_QUOTA_BACKOFF  = 1.2      # seconds to wait before the single retry


class DeezerClient:
    BASE = "https://api.deezer.com"

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": "musicgateway/0.1"},
        )
        self._sem = asyncio.Semaphore(_MAX_CONCURRENCY)
        self._cache: dict[str, tuple[float, dict]] = {}

    async def close(self):
        await self.client.aclose()

    # ── search ────────────────────────────────────────────────────────────────

    async def search(self, query: str, limit: int = 20) -> dict:
        """
        Parallel search across artists, albums, and tracks — returned already
        normalised to the clean Artist/Album/Track shapes the REST API serves
        (see normalize_* below).
        """
        artists, albums, tracks = await asyncio.gather(
            self._get("/search/artist", q=query, limit=limit),
            self._get("/search/album",  q=query, limit=limit),
            self._get("/search/track",  q=query, limit=limit),
            return_exceptions=True,
        )
        return {
            "artists": [normalize_artist(a) for a in _data_or_empty(artists)],
            "albums":  [normalize_album(a)  for a in _data_or_empty(albums)],
            "tracks":  [normalize_track(t)  for t in _data_or_empty(tracks)],
        }

    # ── browse ────────────────────────────────────────────────────────────────

    async def get_artist(self, artist_id: int) -> dict:
        return await self._get(f"/artist/{artist_id}")

    async def get_artist_albums(self, artist_id: int, limit: int = 100) -> list:
        data = await self._get(f"/artist/{artist_id}/albums", limit=limit)
        return data.get("data", []) if isinstance(data, dict) else []

    async def get_artist_top_tracks(self, artist_id: int, limit: int = 20) -> list:
        data = await self._get(f"/artist/{artist_id}/top", limit=limit)
        return data.get("data", []) if isinstance(data, dict) else []

    async def get_album(self, album_id: int) -> dict:
        return await self._get(f"/album/{album_id}")

    async def get_track(self, track_id: int) -> dict:
        return await self._get(f"/track/{track_id}")

    async def get_track_preview_url(self, track_id: int) -> str:
        """Return a track's 30-second preview MP3 URL ('' if none/unavailable)."""
        track = await self.get_track(track_id)
        return track.get("preview", "") if isinstance(track, dict) else ""

    # ── radio / recommendations ─────────────────────────────────────────────
    # NB: Deezer has no working per-track radio endpoint, so radio.py resolves
    # track/album seeds to their artist and uses artist radio below.

    async def get_artist_radio(self, artist_id: int, limit: int = 25) -> list:
        data = await self._get(f"/artist/{artist_id}/radio", limit=limit)
        return data.get("data", []) if isinstance(data, dict) else []

    # ── internal ──────────────────────────────────────────────────────────────

    def _cache_key(self, path: str, params: dict) -> str:
        return path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))

    async def _get(self, path: str, **params) -> dict:
        key = self._cache_key(path, params)
        hit = self._cache.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]

        data = await self._fetch(path, params)

        # Only cache truthy payloads — never cache an empty/error result,
        # so a transient quota blip doesn't get pinned for 5 minutes.
        if data:
            if len(self._cache) >= _CACHE_MAX:
                self._cache.clear()
            self._cache[key] = (time.monotonic() + _CACHE_TTL, data)
        return data

    async def _fetch(self, path: str, params: dict) -> dict:
        for attempt in (1, 2):
            try:
                async with self._sem:
                    r = await self.client.get(f"{self.BASE}{path}", params=params)
                r.raise_for_status()
                data = r.json()
            except Exception as exc:
                log.warning("Deezer request failed (%s): %s", path, exc)
                return {}

            # Deezer signals rate-limiting as HTTP 200 + {"error":{"code":4}}.
            err = data.get("error") if isinstance(data, dict) else None
            if err:
                if err.get("code") == 4 and attempt == 1:
                    log.warning("Deezer quota hit on %s — retrying in %.1fs",
                                path, _QUOTA_BACKOFF)
                    await asyncio.sleep(_QUOTA_BACKOFF)
                    continue
                log.warning("Deezer error on %s: %s", path, err)
                return {}
            return data
        return {}


def _data_or_empty(result) -> list:
    if isinstance(result, dict):
        return result.get("data", [])
    return []


# ── normalizers: raw Deezer shapes → clean REST objects ────────────────────────
# These are the shapes documented in MVP_SPEC (ArtistObject / AlbumObject /
# TrackObject). Keeping them here (not in main.py) means every route — search and
# browse alike — serves identical shapes.

def _year_from_release_date(date: str) -> int:
    if not date or len(date) < 4:
        return 0
    try:
        return int(date[:4])
    except ValueError:
        return 0


def _best_artist_cover(dz: dict) -> str:
    return (dz.get("picture_xl") or dz.get("picture_big")
            or dz.get("picture_medium") or dz.get("picture") or "")


def _best_album_cover(dz: dict) -> str:
    return (dz.get("cover_xl") or dz.get("cover_big")
            or dz.get("cover_medium") or dz.get("cover") or "")


def normalize_artist(dz: dict) -> dict:
    aid = dz.get("id")
    return {
        "id":         aid,
        "name":       dz.get("name", ""),
        "cover_url":  _best_artist_cover(dz),
        "nb_album":   dz.get("nb_album", 0),
        "deezer_url": dz.get("link") or (f"https://www.deezer.com/artist/{aid}" if aid else ""),
    }


def normalize_album(dz: dict, fallback_artist: Optional[dict] = None) -> dict:
    """
    fallback_artist fills artist name/id when the album came from
    /artist/{id}/albums (which omits the artist sub-object).
    """
    aid    = dz.get("id")
    artist = dz.get("artist") or fallback_artist or {}
    return {
        "id":           aid,
        "title":        dz.get("title", ""),
        "artist_name":  artist.get("name", ""),
        "artist_id":    artist.get("id"),
        "cover_url":    _best_album_cover(dz),
        "nb_tracks":    dz.get("nb_tracks", 0),
        "release_year": _year_from_release_date(dz.get("release_date", "")),
        "deezer_url":   dz.get("link") or (f"https://www.deezer.com/album/{aid}" if aid else ""),
    }


def normalize_track(
    dz: dict,
    fallback_album: Optional[dict] = None,
    track_no: Optional[int] = None,
) -> dict:
    """
    fallback_album fills album fields when the track was fetched in an album
    context (Deezer omits the album sub-object there). track_no lets the album
    route supply an enumerated position (album-embedded tracks lack one).
    """
    album  = dz.get("album") or fallback_album or {}
    artist = dz.get("artist") or {}
    return {
        "id":          dz.get("id"),
        "title":       dz.get("title", ""),
        "artist_name": artist.get("name", ""),
        "artist_id":   artist.get("id"),
        "album_title": album.get("title", ""),
        "album_id":    album.get("id"),
        "cover_url":   _best_album_cover(album),
        "duration":    dz.get("duration", 0),     # REAL track length, for display
        "preview_url": dz.get("preview", ""),      # always a 30s clip
        "track_no":    track_no if track_no is not None else dz.get("track_position", 0),
    }
