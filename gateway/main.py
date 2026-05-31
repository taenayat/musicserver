"""
main.py — Music Gateway REST API.

The gateway is a standalone Deezer download manager with a web UI. It no longer
proxies Subsonic — Symfonium talks to Navidrome directly. This app serves:

  • GET  /health                  liveness (+ optional API-key check, see below)
  • /api/*                        JSON REST, all guarded by a single API key
  • /                             the built React frontend (static files)

Lifespan wires up the SQLite queue (db), the Deezer client, the Navidrome client
(for scan triggers), and the deemix-backed Downloader worker.
"""

import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import deezer_api
from auth import api_key_dep, verify_key
from db import Database, init_db
from deezer_api import DeezerClient
from downloader import Downloader
from navidrome import NavidromeClient

# ── Setup ─────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s  %(levelname)-7s  %(name)-12s  %(message)s",
)
log = logging.getLogger("gateway")

DB_PATH   = os.environ.get("DB_PATH", "/data/gateway.db")
MUSIC_DIR = os.environ.get("MUSIC_DIR", "/music")
DIST_DIR  = Path(__file__).parent / "frontend" / "dist"

# Shared, lifespan-managed singletons. Accessed in routes through the get_*
# dependencies below so tests can override them without booting the lifespan.
deezer:     Optional[DeezerClient]  = None
navidrome:  Optional[NavidromeClient] = None
downloader: Optional[Downloader]    = None
db:         Optional[Database]      = None

# Plain client for proxying preview audio + cover images (not a Deezer API call).
http = httpx.AsyncClient(timeout=30.0, follow_redirects=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global deezer, navidrome, downloader, db

    db        = await init_db(DB_PATH)
    deezer    = DeezerClient()
    navidrome = NavidromeClient()
    downloader = Downloader(
        arl       = os.environ["DEEZER_ARL"],
        music_dir = MUSIC_DIR,
        navidrome = navidrome,
        db        = db,
    )
    await downloader.start()
    log.info("gateway ready (db=%s, music=%s)", DB_PATH, MUSIC_DIR)
    try:
        yield
    finally:
        if downloader:
            await downloader.stop()
        if deezer:
            await deezer.close()
        if navidrome:
            await navidrome.close()
        if db:
            await db.close()
        await http.aclose()


app = FastAPI(title="Music Gateway", lifespan=lifespan)

# Single-user local deployment — allow any origin (the dev frontend runs on a
# different port via Vite, and PWAs may load from a different host).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Service accessors (dependency-injected so tests can override) ──────────────

def get_deezer() -> DeezerClient:
    if deezer is None:
        raise HTTPException(503, "Service starting up")
    return deezer


def get_db() -> Database:
    if db is None:
        raise HTTPException(503, "Service starting up")
    return db


def get_downloader() -> Downloader:
    if downloader is None:
        raise HTTPException(503, "Service starting up")
    return downloader


# ── Models ────────────────────────────────────────────────────────────────────

class DownloadRequest(BaseModel):
    type: str                       # 'track' | 'album'
    deezer_id: int
    title: Optional[str] = None
    artist: Optional[str] = None
    cover_url: Optional[str] = None


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health(authorization: Optional[str] = Header(default=None)):
    """
    Liveness probe — callable with no key. The frontend login screen also calls
    this WITH a bearer token to validate the key, so if a token is supplied it
    must be correct (401 otherwise). No token → plain 200 liveness.
    """
    if authorization is not None:
        verify_key(authorization)        # raises 401 if the supplied key is wrong
    return {"status": "ok", "arl_ok": bool(downloader and downloader.arl_ok)}


# ── Search ────────────────────────────────────────────────────────────────────

@app.get("/api/search", dependencies=[api_key_dep])
async def api_search(q: str = "", limit: int = 20, dz: DeezerClient = Depends(get_deezer)):
    query = q.strip()
    if not query:
        return {"artists": [], "albums": [], "tracks": []}
    limit = max(1, min(limit, 50))
    return await dz.search(query, limit=limit)


# ── Browse ────────────────────────────────────────────────────────────────────

@app.get("/api/artist/{deezer_id}", dependencies=[api_key_dep])
async def api_artist(deezer_id: int, dz: DeezerClient = Depends(get_deezer)):
    info, albums, top = await asyncio.gather(
        dz.get_artist(deezer_id),
        dz.get_artist_albums(deezer_id),
        dz.get_artist_top_tracks(deezer_id, limit=10),
    )
    if not info:
        raise HTTPException(404, "Artist not found")

    artist_obj = deezer_api.normalize_artist(info)
    fallback   = {"id": info.get("id"), "name": info.get("name", "")}
    album_objs = [deezer_api.normalize_album(a, fallback_artist=fallback) for a in albums]
    album_objs.sort(key=lambda a: a.get("release_year") or 0, reverse=True)
    top_tracks = [deezer_api.normalize_track(t) for t in top[:10]]

    return {"artist": artist_obj, "albums": album_objs, "top_tracks": top_tracks}


@app.get("/api/album/{deezer_id}", dependencies=[api_key_dep])
async def api_album(deezer_id: int, dz: DeezerClient = Depends(get_deezer)):
    album = await dz.get_album(deezer_id)
    if not album:
        raise HTTPException(404, "Album not found")

    album_obj = deezer_api.normalize_album(album)
    tracks    = album.get("tracks", {}).get("data", [])
    track_objs = [
        deezer_api.normalize_track(t, fallback_album=album, track_no=i + 1)
        for i, t in enumerate(tracks)
    ]
    return {"album": album_obj, "tracks": track_objs}


# ── Preview ───────────────────────────────────────────────────────────────────

@app.get("/api/preview/{track_id}", dependencies=[api_key_dep])
async def api_preview(track_id: int, dz: DeezerClient = Depends(get_deezer)):
    preview_url = await dz.get_track_preview_url(track_id)
    if not preview_url:
        return JSONResponse({"error": "No preview available for this track"},
                            status_code=404)

    async def gen():
        async with http.stream("GET", preview_url) as resp:
            async for chunk in resp.aiter_bytes():
                yield chunk

    # Stream directly — never cache audio (PWA service worker also skips it).
    return StreamingResponse(gen(), media_type="audio/mpeg",
                             headers={"Cache-Control": "no-store"})


# ── Downloads ─────────────────────────────────────────────────────────────────

@app.post("/api/download", dependencies=[api_key_dep])
async def api_download(req: DownloadRequest, dl: Downloader = Depends(get_downloader)):
    if req.type not in ("track", "album"):
        raise HTTPException(400, "type must be 'track' or 'album'")
    dl_id = await dl.enqueue(
        req.type, req.deezer_id,
        title=req.title, artist=req.artist, cover_url=req.cover_url,
    )
    return {"id": dl_id, "status": "pending"}


@app.get("/api/queue", dependencies=[api_key_dep])
async def api_queue(limit: int = 50, store: Database = Depends(get_db)):
    limit = max(1, min(limit, 200))
    items = await store.get_queue(limit=limit)
    return {"items": items}


@app.delete("/api/queue/{item_id}", dependencies=[api_key_dep])
async def api_queue_delete(item_id: int, store: Database = Depends(get_db)):
    item = await store.get_download(item_id)
    if not item:
        raise HTTPException(404, "Queue item not found")
    if item["status"] == "downloading":
        raise HTTPException(409, "Cannot remove an in-progress download")
    await store.delete_download(item_id)
    return Response(status_code=204)


# ── Cover art proxy ───────────────────────────────────────────────────────────

# Only proxy Deezer's own image CDN — keeps this from being a general-purpose
# open relay (SSRF). The frontend only ever passes Deezer cover URLs here.
_COVER_HOSTS = ("dzcdn.net", "deezer.com")
_SIZE_PX     = {"sm": "250x250", "md": "500x500", "lg": "1000x1000"}


def _cover_allowed(url: str) -> bool:
    parts = urlparse(url)
    if parts.scheme not in ("http", "https"):
        return False
    host = (parts.hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _COVER_HOSTS)


def _resize_cover(url: str, size: str) -> str:
    px = _SIZE_PX.get(size)
    if not px:
        return url
    # Deezer covers carry a WxH segment, e.g. .../500x500-000000-80-0-0.jpg
    return re.sub(r"\d+x\d+", px, url, count=1)


@app.get("/api/cover", dependencies=[api_key_dep])
async def api_cover(url: str, size: str = "md"):
    if not _cover_allowed(url):
        raise HTTPException(400, "Only Deezer cover URLs may be proxied")
    try:
        r = await http.get(_resize_cover(url, size))
        r.raise_for_status()
    except Exception:
        raise HTTPException(404, "Cover not found")
    return Response(
        content=r.content,
        media_type=r.headers.get("content-type", "image/jpeg"),
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ── Static frontend (MUST be mounted last) ────────────────────────────────────

if DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="frontend")
    log.info("serving frontend from %s", DIST_DIR)
else:
    log.warning("frontend bundle not found at %s — UI not served. "
                "Run `npm run build` in gateway/frontend (Docker does this).", DIST_DIR)
