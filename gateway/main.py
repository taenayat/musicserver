"""
main.py — Music Gateway REST API.

A standalone Deezer/YouTube download manager + library/cache/radio/lyrics
service with a multi-user web UI. Symfonium streams from Navidrome directly;
this app manages everything around it.

Layout (see SPEC_COMPLETE.txt):
  • GET  /health                liveness + feature flags + first_run
  • POST /api/auth/*            login / logout / me (no session required to login)
  • /api/*                      session-guarded JSON REST (some admin-only)
  • /                           the built React frontend (mounted LAST)

Lifespan wires the SQLite DB, the Deezer/Navidrome/Telegram clients, the
deemix+yt-dlp Downloader worker, and the radio-cleanup / metrics / cache-manager
background loops.
"""

import asyncio
import datetime as _dt
import logging
import logging.handlers
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import artwork
import auth
import cache as cache_mod
import deezer_api
import library
import lyrics as lyrics_mod
import radio as radio_mod
import ytdlp
from auth import get_current_user, require_admin
from cache import CacheConfig
from db import Database, init_db
from deezer_api import DeezerClient
from downloader import Downloader
from navidrome import NavidromeClient
from telegram import TelegramClient

VERSION = "1.0.0"

DB_PATH   = os.environ.get("DB_PATH", "/data/gateway.db")
MUSIC_DIR = os.environ.get("MUSIC_DIR", "/music")
LOG_FILE  = os.environ.get("LOG_FILE", "/data/gateway.log")
DIST_DIR  = Path(__file__).parent / "frontend" / "dist"

RADIO_ENABLED = os.environ.get("RADIO_ENABLED", "true").lower() in ("1", "true", "yes")
RADIO_TRACK_COUNT = int(os.environ.get("RADIO_TRACK_COUNT", "20"))
RADIO_TTL_HOURS = int(os.environ.get("RADIO_TTL_HOURS", "24"))


# ── logging: stdout + rotating file ─────────────────────────────────────────

def _configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)-12s  %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=3)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception as exc:  # pragma: no cover
        root.warning("could not open log file %s: %s", LOG_FILE, exc)


_configure_logging()
log = logging.getLogger("gateway")

# Shared singletons (set in lifespan).
deezer:     Optional[DeezerClient]   = None
navidrome:  Optional[NavidromeClient] = None
telegram:   Optional[TelegramClient] = None
downloader: Optional[Downloader]     = None
db:         Optional[Database]       = None
cache_config: Optional[CacheConfig]  = None

IS_FIRST_RUN = False
START_TIME = time.time()
_LOG_ERRORS: list[float] = []

http = httpx.AsyncClient(timeout=20.0, follow_redirects=True)
_bg_tasks: list[asyncio.Task] = []


class _ErrorCounter(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            _LOG_ERRORS.append(time.time())


logging.getLogger().addHandler(_ErrorCounter())


# ── telegram inbound ingest ──────────────────────────────────────────────────

_TG_OFFSET_KEY = "telegram_update_offset"
_TG_MAX_BYTES = 20 * 1024 * 1024  # Bot API getFile download cap (~20MB)
_MIME_EXT = {
    "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a",
    "audio/flac": ".flac", "audio/x-flac": ".flac", "audio/ogg": ".ogg",
    "audio/opus": ".opus", "audio/aac": ".aac", "audio/wav": ".wav",
}


def _tg_sanitize(name: str) -> str:
    name = (name or "").strip() or "Unknown"
    return re.sub(r'[<>:"/\\|?*]', "_", name)


async def _tg_get_offset() -> int:
    v = await db.get_setting(_TG_OFFSET_KEY)
    try:
        return int(v) if v else 0
    except (TypeError, ValueError):
        return 0


async def _tg_set_offset(offset: int) -> None:
    await db.set_setting(_TG_OFFSET_KEY, str(offset))


async def _telegram_import_audio(audio: dict, msg: dict) -> None:
    """Import one audio message from the channel into the library."""
    if audio.get("from_bot"):
        return  # the gateway's own uploads — ignore to avoid an import/upload loop
    size = audio.get("file_size") or 0
    if size and size > _TG_MAX_BYTES:
        log.warning("telegram import: %.1f MB exceeds Bot API getFile limit; skipping",
                    size / 1e6)
        return

    performer = audio.get("performer") or "Unknown Artist"
    title = audio.get("title")
    ext = _MIME_EXT.get((audio.get("mime") or "").lower(), "")
    file_name = audio.get("file_name") or ((title or "track") + (ext or ".mp3"))
    dest_dir = os.path.join(MUSIC_DIR, _tg_sanitize(performer), "Telegram")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, _tg_sanitize(os.path.basename(file_name)))

    await telegram.download_file(audio["file_id"], dest)
    rel = os.path.relpath(dest, MUSIC_DIR)
    tags = await asyncio.to_thread(library._read_tags, dest, rel)

    existing = await library.is_in_library(
        {"id": None, "title": tags.get("title"),
         "artist_name": tags.get("artist"), "duration": tags.get("duration_sec")}, db)
    if existing and existing.get("file_path") != rel:
        try:
            os.remove(dest)
        except OSError:
            pass
        log.info("telegram import: duplicate of %s, skipped", existing["file_path"])
        return

    await db.upsert_library_track(file_path=rel, location="local", **tags)
    # Mark Telegram-backed so the outbound backup never re-uploads it.
    await db.set_telegram_backed(rel, msg.get("message_id"), audio["file_id"])
    await db.add_telegram_file(rel, msg.get("message_id"), audio["file_id"],
                               tags.get("file_size_mb"))
    await navidrome.trigger_scan()
    log.info("telegram import: added %s", rel)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global deezer, navidrome, telegram, downloader, db, cache_config, IS_FIRST_RUN

    db = await init_db(DB_PATH)
    auth.set_db_getter(lambda: db)

    IS_FIRST_RUN = (await db.count_users()) == 0
    if IS_FIRST_RUN:
        log.info("first run: no users yet — frontend will show create-admin screen")

    deezer    = DeezerClient()
    navidrome = NavidromeClient()

    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_channel = os.environ.get("TELEGRAM_CHANNEL_ID", "")
    if tg_token and tg_channel:
        telegram = TelegramClient(http, tg_token, tg_channel)
        telegram.start()
        telegram.start_inbound(_telegram_import_audio, _tg_get_offset, _tg_set_offset)

    downloader = Downloader(
        arl=os.environ["DEEZER_ARL"], music_dir=MUSIC_DIR,
        navidrome=navidrome, db=db, telegram=telegram, http=http)
    await downloader.start()

    cache_config = CacheConfig.from_env()

    if RADIO_ENABLED:
        _bg_tasks.append(asyncio.create_task(
            radio_mod.cleanup_loop(db, navidrome, MUSIC_DIR)))
    _bg_tasks.append(asyncio.create_task(collect_metrics_loop()))
    if cache_config.enabled:
        _bg_tasks.append(asyncio.create_task(
            cache_mod.run_cache_manager(db, telegram, navidrome, cache_config)))

    log.info("gateway ready (db=%s, music=%s, first_run=%s)",
             DB_PATH, MUSIC_DIR, IS_FIRST_RUN)
    try:
        yield
    finally:
        for t in _bg_tasks:
            t.cancel()
        if downloader:
            await downloader.stop()
        if telegram:
            await telegram.stop()
        if deezer:
            await deezer.close()
        if navidrome:
            await navidrome.close()
        if db:
            await db.close()
        await http.aclose()


app = FastAPI(title="Music Gateway", version=VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


# ── service accessors ───────────────────────────────────────────────────────

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


def get_navidrome() -> NavidromeClient:
    if navidrome is None:
        raise HTTPException(503, "Service starting up")
    return navidrome


# ── models ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: Optional[str] = None
    new_password: str


class CreateUser(BaseModel):
    username: str
    password: str
    role: str = "user"


class PatchUser(BaseModel):
    role: Optional[str] = None
    password: Optional[str] = None


class DownloadRequest(BaseModel):
    source: str = "deezer"
    type: Optional[str] = None
    deezer_id: Optional[int] = None
    yt_id: Optional[str] = None
    yt_query: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    cover_url: Optional[str] = None
    force: bool = False


class RadioStart(BaseModel):
    seed_type: str
    seed_deezer_id: int
    seed_title: str
    seed_cover_url: Optional[str] = None


class RadioLike(BaseModel):
    deezer_track_id: int


class RecallRequest(BaseModel):
    file_path: str


class ArtApply(BaseModel):
    track_ids: list[int]


# ── health (no auth) ─────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "first_run": IS_FIRST_RUN,
        "arl_ok": bool(downloader and downloader.arl_ok),
        "version": VERSION,
        "radio_enabled": RADIO_ENABLED,
        "ytdlp_enabled": ytdlp.is_enabled(),
        "lyrics_enabled": lyrics_mod.is_enabled(),
        "cache_enabled": bool(cache_config and cache_config.enabled),
    }


# ── auth ─────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
async def login(req: LoginRequest, store: Database = Depends(get_db)):
    user = await store.get_user_by_username(req.username.strip())
    if not user or not auth.check_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    token = await store.create_session(user["id"], ttl_days=auth.SESSION_TTL_DAYS)
    return {"token": token, "role": user["role"], "username": user["username"]}


@app.post("/api/auth/logout")
async def logout(authorization: Optional[str] = Header(default=None),
                 store: Database = Depends(get_db)):
    _, _, token = (authorization or "").partition(" ")
    if token:
        await store.delete_session(token.strip())
    return {"status": "ok"}


@app.get("/api/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return auth.public_user(user)


@app.patch("/api/auth/me/password")
async def change_my_password(req: PasswordChange,
                             user: dict = Depends(get_current_user),
                             store: Database = Depends(get_db)):
    if not req.current_password or not auth.check_password(
            req.current_password, user["password_hash"]):
        raise HTTPException(403, "Current password is incorrect")
    if len(req.new_password) < 4:
        raise HTTPException(400, "New password too short")
    await auth.change_password(store, navidrome, user, req.new_password)
    return {"status": "ok"}


# ── status (any user) ─────────────────────────────────────────────────────────

@app.get("/api/status")
async def status(user: dict = Depends(get_current_user),
                 store: Database = Depends(get_db)):
    counts = await store.count_downloads_by_status()
    local_gb = await store.get_cache_size_gb()
    limit = cache_config.size_gb if cache_config else float(os.environ.get("CACHE_SIZE_GB", "20"))
    return {
        "queue_pending": counts.get("pending", 0),
        "queue_downloading": counts.get("downloading", 0),
        "storage_gb_used": local_gb,
        "storage_gb_limit": limit,
        "server_ok": bool(downloader and downloader.arl_ok),
        "recall_in_progress": False,
    }


# ── search ─────────────────────────────────────────────────────────────────────

@app.get("/api/search")
async def api_search(q: str = "", limit: int = 20,
                     user: dict = Depends(get_current_user),
                     dz: DeezerClient = Depends(get_deezer),
                     store: Database = Depends(get_db)):
    query = q.strip()
    if not query:
        return {"artists": [], "albums": [], "tracks": []}
    limit = max(1, min(limit, 50))
    result = await dz.search(query, limit=limit)
    await library.enrich_with_library(result.get("tracks", []), store)
    return result


@app.get("/api/search/youtube")
async def api_search_youtube(q: str = "", limit: int = 10,
                             user: dict = Depends(get_current_user),
                             store: Database = Depends(get_db)):
    if not ytdlp.is_enabled():
        raise HTTPException(503, "YouTube search is disabled")
    query = q.strip()
    if not query:
        return {"tracks": []}
    limit = max(1, min(limit, 25))
    results = await ytdlp.search_youtube_music(query, limit=limit)
    for t in results:
        t["in_library"] = False
        t["library_path"] = None
    return {"tracks": results}


# ── browse ─────────────────────────────────────────────────────────────────────

@app.get("/api/artist/{deezer_id}")
async def api_artist(deezer_id: int, user: dict = Depends(get_current_user),
                     dz: DeezerClient = Depends(get_deezer),
                     store: Database = Depends(get_db)):
    info, albums, top = await asyncio.gather(
        dz.get_artist(deezer_id),
        dz.get_artist_albums(deezer_id),
        dz.get_artist_top_tracks(deezer_id, limit=10),
    )
    if not info:
        raise HTTPException(404, "Artist not found")
    artist_obj = deezer_api.normalize_artist(info)
    fallback = {"id": info.get("id"), "name": info.get("name", "")}
    album_objs = [deezer_api.normalize_album(a, fallback_artist=fallback) for a in albums]
    album_objs.sort(key=lambda a: a.get("release_year") or 0, reverse=True)
    top_tracks = [deezer_api.normalize_track(t) for t in top[:10]]
    await library.enrich_with_library(top_tracks, store)
    return {"artist": artist_obj, "albums": album_objs, "top_tracks": top_tracks}


@app.get("/api/album/{deezer_id}")
async def api_album(deezer_id: int, user: dict = Depends(get_current_user),
                    dz: DeezerClient = Depends(get_deezer),
                    store: Database = Depends(get_db)):
    album = await dz.get_album(deezer_id)
    if not album:
        raise HTTPException(404, "Album not found")
    album_obj = deezer_api.normalize_album(album)
    tracks = album.get("tracks", {}).get("data", [])
    track_objs = [
        deezer_api.normalize_track(t, fallback_album=album, track_no=i + 1)
        for i, t in enumerate(tracks)
    ]
    await library.enrich_with_library(track_objs, store)
    return {"album": album_obj, "tracks": track_objs}


# ── preview ─────────────────────────────────────────────────────────────────────

@app.get("/api/preview/{track_id}")
async def api_preview(track_id: int, user: dict = Depends(get_current_user),
                      dz: DeezerClient = Depends(get_deezer)):
    preview_url = await dz.get_track_preview_url(track_id)
    if not preview_url:
        return JSONResponse({"error": "No preview available"}, status_code=404)

    async def gen():
        async with http.stream("GET", preview_url) as resp:
            async for chunk in resp.aiter_bytes():
                yield chunk

    return StreamingResponse(gen(), media_type="audio/mpeg",
                             headers={"Cache-Control": "no-store"})


# ── downloads ───────────────────────────────────────────────────────────────

@app.post("/api/download")
async def api_download(req: DownloadRequest,
                       user: dict = Depends(get_current_user),
                       dl: Downloader = Depends(get_downloader),
                       store: Database = Depends(get_db)):
    if req.source == "deezer":
        if req.type not in ("track", "album"):
            raise HTTPException(400, "type must be 'track' or 'album'")
        if not req.force and req.type == "track" and req.deezer_id:
            row = await library.is_in_library(
                {"id": req.deezer_id, "title": req.title,
                 "artist_name": req.artist}, store)
            if row:
                return {"status": "already_in_library",
                        "file_path": row["file_path"],
                        "format": row.get("format"),
                        "bitrate_kbps": row.get("bitrate_kbps")}
        dl_id = await dl.enqueue("deezer", deezer_type=req.type,
                                 deezer_id=req.deezer_id, title=req.title,
                                 artist=req.artist, cover_url=req.cover_url,
                                 requested_by=user["id"])
    elif req.source == "youtube":
        if not ytdlp.is_enabled():
            raise HTTPException(503, "YouTube downloads are disabled")
        if not req.yt_id:
            raise HTTPException(400, "yt_id is required for youtube source")
        dl_id = await dl.enqueue("youtube", yt_id=req.yt_id,
                                 yt_query=req.yt_query or req.yt_id,
                                 title=req.title, artist=req.artist,
                                 cover_url=req.cover_url, requested_by=user["id"])
    else:
        raise HTTPException(400, "source must be 'deezer' or 'youtube'")
    return {"id": dl_id, "status": "pending"}


@app.get("/api/queue")
async def api_queue(limit: int = 50, offset: int = 0,
                    user: dict = Depends(get_current_user),
                    store: Database = Depends(get_db)):
    limit = max(1, min(limit, 200))
    items = await store.get_queue(limit=limit, offset=max(0, offset))
    return {"items": items}


@app.delete("/api/queue/{item_id}")
async def api_queue_delete(item_id: int, user: dict = Depends(get_current_user),
                           store: Database = Depends(get_db)):
    item = await store.get_download(item_id)
    if not item:
        raise HTTPException(404, "Queue item not found")
    if item["status"] == "downloading":
        raise HTTPException(409, "Cannot remove an in-progress download")
    await store.delete_download(item_id)
    return Response(status_code=204)


# ── library ─────────────────────────────────────────────────────────────────

_scan_in_progress = False


@app.get("/api/library/stats")
async def api_library_stats(user: dict = Depends(get_current_user),
                            store: Database = Depends(get_db)):
    stats = await store.library_stats()
    stats["scan_in_progress"] = _scan_in_progress
    stats["last_scan"] = await store.get_setting("last_library_scan")
    return stats


async def _run_library_scan(store: Database):
    global _scan_in_progress
    _scan_in_progress = True
    try:
        result = await library.scan_library(MUSIC_DIR, store)
        await store.set_setting(
            "last_library_scan",
            _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        log.info("library scan complete: %s", result)
    except Exception as exc:
        log.error("library scan failed: %s", exc)
    finally:
        _scan_in_progress = False


@app.post("/api/library/scan")
async def api_library_scan(admin: dict = Depends(require_admin),
                           store: Database = Depends(get_db)):
    if not _scan_in_progress:
        asyncio.create_task(_run_library_scan(store))
    return {"status": "scan_started"}


@app.delete("/api/library/tracks/{track_id}")
async def api_delete_track(track_id: int,
                           user: dict = Depends(get_current_user),
                           store: Database = Depends(get_db),
                           nav: NavidromeClient = Depends(get_navidrome)):
    track = await store.get_library_track(track_id)
    if not track:
        raise HTTPException(404, "Track not found")
    await _delete_one_track(track, user, store)
    await nav.trigger_scan()
    return {"status": "deleted"}


async def _delete_one_track(track: dict, user: dict, store: Database):
    # Case 3: part of an active radio session.
    active = await store.radio_track_active_for_path(track["file_path"])
    if active:
        raise HTTPException(409, "File is part of an active radio session")
    backed = track.get("telegram_backed")
    if backed and user.get("role") != "admin":
        raise HTTPException(
            403, "This track exists in shared storage. Only an admin can delete it.")
    abs_path = os.path.join(MUSIC_DIR, track["file_path"])
    if os.path.isfile(abs_path):
        try:
            os.remove(abs_path)
        except OSError as exc:
            log.warning("could not remove %s: %s", abs_path, exc)
    if backed and track.get("telegram_msg_id") and telegram:
        await telegram.delete_message(track["telegram_msg_id"])
        await store.delete_telegram_file(track["file_path"])
    await store.delete_library_track(track["id"])


@app.delete("/api/library/albums/{deezer_album_id}")
async def api_delete_album(deezer_album_id: int,
                           user: dict = Depends(get_current_user),
                           store: Database = Depends(get_db),
                           nav: NavidromeClient = Depends(get_navidrome)):
    tracks = await store.get_library_tracks_by_album(deezer_album_id)
    if not tracks:
        raise HTTPException(404, "No library tracks for this album")
    if any(t.get("telegram_backed") for t in tracks) and user.get("role") != "admin":
        raise HTTPException(403, "Album contains shared-storage tracks; admin required")
    for t in tracks:
        try:
            await _delete_one_track(t, user, store)
        except HTTPException as exc:
            if exc.status_code == 409:
                raise
    await nav.trigger_scan()
    return {"status": "deleted", "count": len(tracks)}


# ── cover proxy ───────────────────────────────────────────────────────────────

_COVER_HOSTS = ("dzcdn.net", "deezer.com")
_SIZE_PX = {"sm": "250x250", "md": "500x500", "lg": "1000x1000"}


def _cover_allowed(url: str) -> bool:
    parts = urlparse(url)
    if parts.scheme not in ("http", "https"):
        return False
    host = (parts.hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _COVER_HOSTS)


def _resize_cover(url: str, size: str) -> str:
    px = _SIZE_PX.get(size)
    return re.sub(r"\d+x\d+", px, url, count=1) if px else url


@app.get("/api/cover")
async def api_cover(url: str, size: str = "md",
                    user: dict = Depends(get_current_user)):
    if not _cover_allowed(url):
        raise HTTPException(400, "Only Deezer cover URLs may be proxied")
    try:
        r = await http.get(_resize_cover(url, size))
        r.raise_for_status()
    except Exception:
        raise HTTPException(404, "Cover not found")
    return Response(content=r.content,
                    media_type=r.headers.get("content-type", "image/jpeg"),
                    headers={"Cache-Control": "public, max-age=86400"})


# ── admin: users ──────────────────────────────────────────────────────────────

@app.get("/api/admin/users")
async def api_list_users(admin: dict = Depends(require_admin),
                         store: Database = Depends(get_db)):
    users = await store.list_users()
    last_seen = await store.get_user_last_seen()
    now = _dt.datetime.now(_dt.timezone.utc)
    out = []
    for u in users:
        pub = auth.public_user(u)
        ls = last_seen.get(u["id"])
        pub["last_seen"] = ls
        active = False
        if ls:
            try:
                active = (now - _dt.datetime.fromisoformat(
                    ls.replace("Z", "+00:00"))).total_seconds() < 300
            except Exception:
                pass
        pub["active"] = active
        out.append(pub)
    return out


@app.post("/api/admin/users", status_code=201)
async def api_create_user(req: CreateUser, request: Request,
                          store: Database = Depends(get_db),
                          nav: NavidromeClient = Depends(get_navidrome)):
    # Special case: first-run admin creation needs no auth.
    if IS_FIRST_RUN and (await store.count_users()) == 0:
        user = await auth.create_first_admin(store, req.username, req.password, nav)
        globals()["IS_FIRST_RUN"] = False
        return user
    # Otherwise require admin.
    await require_admin(await get_current_user(request.headers.get("authorization")))
    return await auth.create_linked_user(store, nav, req.username, req.password, req.role)


@app.patch("/api/admin/users/{user_id}")
async def api_patch_user(user_id: int, req: PatchUser,
                         admin: dict = Depends(require_admin),
                         store: Database = Depends(get_db),
                         nav: NavidromeClient = Depends(get_navidrome)):
    target = await store.get_user_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if req.role and req.role in ("admin", "user"):
        await store.update_user_role(user_id, req.role)
        if target.get("navidrome_id"):
            try:
                await nav.update_nav_user(target["navidrome_id"],
                                          is_admin=(req.role == "admin"))
            except Exception as exc:
                log.warning("nav role update failed: %s", exc)
    if req.password:
        await auth.change_password(store, nav, target, req.password)
    return {"status": "ok"}


@app.delete("/api/admin/users/{user_id}")
async def api_delete_user(user_id: int, admin: dict = Depends(require_admin),
                          store: Database = Depends(get_db),
                          nav: NavidromeClient = Depends(get_navidrome)):
    target = await store.get_user_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target["id"] == admin["id"]:
        raise HTTPException(400, "You cannot delete your own account")
    await auth.delete_linked_user(store, nav, target)
    return {"status": "deleted"}


# ── admin: system ──────────────────────────────────────────────────────────────

def _log_errors_last_hour() -> int:
    cutoff = time.time() - 3600
    while _LOG_ERRORS and _LOG_ERRORS[0] < cutoff:
        _LOG_ERRORS.pop(0)
    return len(_LOG_ERRORS)


@app.get("/api/admin/status")
async def api_admin_status(admin: dict = Depends(require_admin),
                           store: Database = Depends(get_db),
                           nav: NavidromeClient = Depends(get_navidrome)):
    import psutil
    proc = psutil.Process()
    vm = psutil.virtual_memory()
    counts = await store.count_downloads_by_status()
    lib_stats = await store.library_stats()
    tg_stats = await store.telegram_stats()
    nav_stats = await nav.server_stats()
    users = await api_list_users(admin, store)
    return {
        "gateway": {
            "version": VERSION,
            "uptime_seconds": int(time.time() - START_TIME),
            "cpu_percent": psutil.cpu_percent(interval=0.0),
            "ram_mb_used": round(proc.memory_info().rss / 1e6, 1),
            "ram_mb_total": round(vm.total / 1e6, 1),
            "log_errors_last_hour": _log_errors_last_hour(),
        },
        "disk": {
            "music_dir_gb": await store.get_cache_size_gb(),
            "music_dir_file_count": lib_stats["total_tracks"],
        },
        "navidrome": {
            "reachable": nav_stats.get("reachable", False),
            "song_count": nav_stats.get("song_count", 0),
            "last_scan": nav_stats.get("last_scan"),
            "scanning": nav_stats.get("scanning", False),
        },
        "deezer": {
            "arl_valid": bool(downloader and downloader.arl_ok),
            "cache_entries": len(deezer._cache) if deezer else 0,
        },
        "telegram": {
            "connected": telegram is not None,
            "backed_up_files": tg_stats["backed_up_files"],
            "pending_uploads": telegram.pending_uploads() if telegram else 0,
            "total_backed_gb": tg_stats["total_backed_gb"],
        },
        "queue": {
            "pending": counts.get("pending", 0),
            "downloading": counts.get("downloading", 0),
            "done_today": await store.count_downloads_today("done"),
            "errors_today": await store.count_downloads_today("error"),
        },
        "library": {
            "total_tracks": lib_stats["total_tracks"],
            "scan_in_progress": _scan_in_progress,
            "last_scan": await store.get_setting("last_library_scan"),
            "formats": lib_stats["formats"],
        },
        "cache": await cache_mod.cache_status(store, cache_config) if cache_config else {},
        "radio": {
            "active_sessions": await store.count_active_radio_sessions(),
            "total_tracks_downloading": await store.count_radio_tracks_downloading(),
        },
        "users": users,
    }


@app.get("/api/admin/logs")
async def api_admin_logs(lines: int = 100, admin: dict = Depends(require_admin)):
    lines = max(1, min(lines, 1000))
    try:
        with open(LOG_FILE, "r", errors="replace") as fh:
            content = fh.readlines()
        return {"lines": [ln.rstrip("\n") for ln in content[-lines:]]}
    except FileNotFoundError:
        return {"lines": []}


@app.post("/api/admin/scan")
async def api_admin_scan(admin: dict = Depends(require_admin),
                         nav: NavidromeClient = Depends(get_navidrome)):
    ok = await nav.trigger_scan()
    if not ok:
        raise HTTPException(502, "Navidrome did not accept the scan request")
    return {"status": "scan_triggered", "ok": True}


@app.post("/api/admin/library/scan")
async def api_admin_library_scan(admin: dict = Depends(require_admin),
                                 store: Database = Depends(get_db)):
    if not _scan_in_progress:
        asyncio.create_task(_run_library_scan(store))
    return {"status": "scan_started"}


@app.post("/api/admin/clear-queue")
async def api_clear_queue(admin: dict = Depends(require_admin),
                          store: Database = Depends(get_db)):
    n = await store.clear_finished_downloads()
    return {"status": "ok", "removed": n}


@app.post("/api/admin/telegram/backfill")
async def api_telegram_backfill(admin: dict = Depends(require_admin),
                                store: Database = Depends(get_db)):
    if not telegram:
        raise HTTPException(503, "Telegram is not configured")
    tracks = await store.get_non_backed_tracks()
    queued = 0
    for t in tracks:
        abs_path = os.path.join(MUSIC_DIR, t["file_path"])
        if os.path.isfile(abs_path):
            telegram.enqueue_upload(
                abs_path, t["file_path"], downloader._make_tg_callback(t["file_path"], -1))
            queued += 1
    return {"queued": queued}


# ── admin: artwork & lyrics backfill ─────────────────────────────────────────

async def _resolve_deezer_cover_url(track: dict, dz: DeezerClient) -> Optional[str]:
    """Best cover URL for a library track from Deezer, or None."""
    dz_id = track.get("deezer_id")
    if dz_id:
        t = await dz.get_track(dz_id)
        album = (t or {}).get("album") or {}
        url = deezer_api._best_album_cover(album)
        if url:
            return url
    alb_id = track.get("deezer_album_id")
    if alb_id:
        album = await dz.get_album(alb_id)
        url = deezer_api._best_album_cover(album or {})
        if url:
            return url
    return None


async def _fetch_and_embed_cover(abs_path: str, url: str) -> bool:
    """Fetch a (trusted) Deezer cover and embed it. Returns True on success."""
    if not _cover_allowed(url) or not artwork.can_embed(abs_path):
        return False
    try:
        r = await http.get(_resize_cover(url, "lg"))
        r.raise_for_status()
        data = r.content
        mime = r.headers.get("content-type", "image/jpeg")
    except Exception:
        return False
    return await asyncio.to_thread(artwork.embed_cover, abs_path, data, mime)


@app.post("/api/admin/art/backfill")
async def api_art_backfill(admin: dict = Depends(require_admin),
                           store: Database = Depends(get_db),
                           dz: DeezerClient = Depends(get_deezer),
                           nav: NavidromeClient = Depends(get_navidrome)):
    tracks = await store.list_all_library_tracks()
    updated = 0
    for t in tracks:
        abs_path = os.path.join(MUSIC_DIR, t["file_path"])
        if not os.path.isfile(abs_path):
            continue
        if not await asyncio.to_thread(artwork.is_missing_art, abs_path):
            continue
        url = await _resolve_deezer_cover_url(t, dz)
        if not url:
            continue
        if await _fetch_and_embed_cover(abs_path, url):
            updated += 1
    if updated:
        await nav.trigger_scan()
    return {"updated": updated, "scanned": len(tracks)}


@app.post("/api/admin/lyrics/backfill")
async def api_lyrics_backfill(admin: dict = Depends(require_admin),
                              store: Database = Depends(get_db),
                              nav: NavidromeClient = Depends(get_navidrome)):
    if not lyrics_mod.is_enabled():
        raise HTTPException(503, "Lyrics are disabled")
    tracks = await store.list_all_library_tracks()
    written = 0
    for t in tracks:
        abs_path = os.path.join(MUSIC_DIR, t["file_path"])
        if not os.path.isfile(abs_path):
            continue
        if os.path.isfile(lyrics_mod.lrc_sidecar_path(abs_path)):
            continue
        lrc = await lyrics_mod.get_synced_lrc(
            http, store, t.get("deezer_id") or 0,
            t.get("title") or "", t.get("artist") or "",
            t.get("album"), t.get("duration_sec"))
        if lrc and await asyncio.to_thread(
                lyrics_mod.write_lrc_sidecar, abs_path, lrc):
            written += 1
    if written:
        await nav.trigger_scan()
    return {"written": written, "scanned": len(tracks)}


# ── admin: album-art sync tool (review + select + apply) ─────────────────────

@app.get("/api/admin/art/missing")
async def api_art_missing(admin: dict = Depends(require_admin),
                          store: Database = Depends(get_db),
                          dz: DeezerClient = Depends(get_deezer)):
    """List library tracks with no cover art, each with a proposed cover."""
    tracks = await store.list_all_library_tracks()
    out = []
    for t in tracks:
        abs_path = os.path.join(MUSIC_DIR, t["file_path"])
        if not os.path.isfile(abs_path):
            continue
        if not await asyncio.to_thread(artwork.is_missing_art, abs_path):
            continue
        url = await _resolve_deezer_cover_url(t, dz)
        out.append({
            "track_id": t["id"],
            "title": t.get("title"),
            "artist": t.get("artist"),
            "album": t.get("album"),
            "file_path": t["file_path"],
            "proposed_cover_url": url,
            "fixable": bool(url) and artwork.can_embed(abs_path),
        })
    return {"tracks": out}


@app.post("/api/admin/art/apply")
async def api_art_apply(req: ArtApply, admin: dict = Depends(require_admin),
                        store: Database = Depends(get_db),
                        dz: DeezerClient = Depends(get_deezer),
                        nav: NavidromeClient = Depends(get_navidrome)):
    """Embed proposed cover art into the selected tracks, then rescan."""
    updated = 0
    for tid in req.track_ids:
        t = await store.get_library_track(tid)
        if not t:
            continue
        abs_path = os.path.join(MUSIC_DIR, t["file_path"])
        if not os.path.isfile(abs_path) or not artwork.can_embed(abs_path):
            continue
        url = await _resolve_deezer_cover_url(t, dz)
        if not url:
            continue
        if await _fetch_and_embed_cover(abs_path, url):
            updated += 1
    if updated:
        await nav.trigger_scan()
    return {"updated": updated, "requested": len(req.track_ids)}


# ── radio ─────────────────────────────────────────────────────────────────────

@app.post("/api/radio")
async def api_radio_start(req: RadioStart, user: dict = Depends(get_current_user),
                          store: Database = Depends(get_db),
                          dz: DeezerClient = Depends(get_deezer),
                          nav: NavidromeClient = Depends(get_navidrome),
                          dl: Downloader = Depends(get_downloader)):
    if not RADIO_ENABLED:
        raise HTTPException(503, "Radio is disabled")
    if req.seed_type not in ("track", "artist", "album"):
        raise HTTPException(400, "seed_type must be track|artist|album")
    try:
        return await radio_mod.start_radio(
            dz, nav, store, dl, user, req.seed_type, req.seed_deezer_id,
            req.seed_title, req.seed_cover_url, RADIO_TRACK_COUNT, RADIO_TTL_HOURS)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/radio")
async def api_radio_list(user: dict = Depends(get_current_user),
                         store: Database = Depends(get_db)):
    sessions = await store.list_radio_sessions(user["id"])
    for s in sessions:
        s["tracks"] = await store.list_radio_tracks(s["id"])
    return {"sessions": sessions}


@app.post("/api/radio/{session_id}/like")
async def api_radio_like(session_id: str, req: RadioLike,
                         user: dict = Depends(get_current_user),
                         store: Database = Depends(get_db),
                         nav: NavidromeClient = Depends(get_navidrome)):
    session = await store.get_radio_session(session_id)
    if not session or session["user_id"] != user["id"]:
        raise HTTPException(404, "Radio session not found")
    try:
        rel = await radio_mod.like_radio_track(
            store, nav, telegram, MUSIC_DIR, session_id, req.deezer_track_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"final_path": rel}


@app.post("/api/radio/{session_id}/dismiss", status_code=202)
async def api_radio_dismiss(session_id: str, user: dict = Depends(get_current_user),
                            store: Database = Depends(get_db),
                            nav: NavidromeClient = Depends(get_navidrome)):
    session = await store.get_radio_session(session_id)
    if not session or session["user_id"] != user["id"]:
        raise HTTPException(404, "Radio session not found")
    asyncio.create_task(radio_mod.dismiss_session(store, nav, MUSIC_DIR, session_id))
    return {"status": "dismissing"}


# ── lyrics ─────────────────────────────────────────────────────────────────────

@app.get("/api/lyrics")
async def api_lyrics(track_id: int = 0, title: str = "", artist: str = "",
                     album: str = "", duration: int = 0,
                     user: dict = Depends(get_current_user),
                     store: Database = Depends(get_db)):
    if not lyrics_mod.is_enabled():
        return {"synced": None, "plain": None, "source": None}
    result = await lyrics_mod.fetch_lyrics(
        http, store, track_id, title, artist, album or None, duration or None)
    return {"synced": result["synced"] or None,
            "plain": result["plain"], "source": result["source"]}


# ── cache ─────────────────────────────────────────────────────────────────────

@app.get("/api/cache/status")
async def api_cache_status(user: dict = Depends(get_current_user),
                           store: Database = Depends(get_db)):
    if not cache_config:
        raise HTTPException(503, "Service starting up")
    return await cache_mod.cache_status(store, cache_config)


@app.post("/api/cache/recall")
async def api_cache_recall(req: RecallRequest,
                           user: dict = Depends(get_current_user),
                           store: Database = Depends(get_db),
                           nav: NavidromeClient = Depends(get_navidrome)):
    if not telegram:
        raise HTTPException(503, "Telegram is not configured")

    async def _do():
        ok = await cache_mod.recall_track(store, telegram, MUSIC_DIR, req.file_path)
        if ok:
            await nav.trigger_scan()

    asyncio.create_task(_do())
    return {"status": "recall_started"}


@app.post("/api/admin/cache/evict")
async def api_cache_evict(admin: dict = Depends(require_admin),
                          store: Database = Depends(get_db),
                          nav: NavidromeClient = Depends(get_navidrome)):
    if not cache_config:
        raise HTTPException(503, "Service starting up")
    return await cache_mod.maybe_evict(store, telegram, nav, cache_config)


@app.post("/api/admin/cache/recall-all")
async def api_cache_recall_all(admin: dict = Depends(require_admin),
                               store: Database = Depends(get_db),
                               nav: NavidromeClient = Depends(get_navidrome)):
    if not telegram:
        raise HTTPException(503, "Telegram is not configured")
    asyncio.create_task(cache_mod.recall_all(store, telegram, nav, MUSIC_DIR))
    return {"status": "recall_all_started"}


# ── admin: metrics ──────────────────────────────────────────────────────────

@app.get("/api/admin/metrics")
async def api_metrics(hours: int = 24, admin: dict = Depends(require_admin),
                      store: Database = Depends(get_db)):
    points = await store.get_metrics_history(max(1, min(hours, 168)))
    per_day = await store.downloads_per_day(7)
    return {"points": points, "downloads_per_day": per_day}


async def collect_metrics_loop():
    import psutil
    while True:
        await asyncio.sleep(300)
        try:
            cpu = await asyncio.to_thread(psutil.cpu_percent, 1.0)
            ram = psutil.Process().memory_info().rss / 1e6
            disk = await db.get_cache_size_gb()
            q = await db.count_active_downloads()
            ua = await db.count_active_sessions(window_minutes=5)
            await db.insert_metrics(cpu, ram, disk, q, ua)
            await db.delete_old_metrics(days=7)
        except Exception as exc:
            log.error("metrics collector error: %s", exc)


# ── static frontend (mounted LAST) ───────────────────────────────────────────

if DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="frontend")
    log.info("serving frontend from %s", DIST_DIR)
else:
    log.warning("frontend bundle not found at %s — UI not served.", DIST_DIR)
