"""
radio.py — seed-based radio sessions.

A user picks a seed (track / artist / album). The gateway fetches
RADIO_TRACK_COUNT related Deezer tracks (skipping ones already in the library),
downloads them all to /music/radio/<session_id>/, and creates a private
Navidrome playlist the user opens in Symfonium. After RADIO_TTL_HOURS or a
manual dismiss, non-liked files are deleted and the playlist removed. Liking a
track moves it into the permanent library (pinned) and backs it up to Telegram.
"""

import asyncio
import datetime as _dt
import logging
import os
import re
import shutil
from typing import Optional

import auth
import library

log = logging.getLogger("radio")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sanitize(name: str) -> str:
    name = (name or "").strip() or "Unknown"
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def playlist_name(seed_title: str) -> str:
    return f"🎲 Radio: {seed_title}"


async def get_radio_tracks(deezer, seed_type: str, seed_deezer_id: int,
                           count: int, db) -> list[dict]:
    """Fetch related tracks, dedupe, drop library duplicates, return `count`.

    Deezer only serves related tracks per *artist* (`/artist/{id}/radio`); there
    is no working per-track radio endpoint. So track and album seeds are resolved
    to their primary artist first, then run through artist radio.
    """
    if seed_type == "artist":
        raw = await deezer.get_artist_radio(seed_deezer_id, limit=count + 10)
    elif seed_type == "track":
        track = await deezer.get_track(seed_deezer_id)
        artist_id = (track.get("artist") or {}).get("id") if track else None
        raw = (await deezer.get_artist_radio(artist_id, limit=count + 10)
               if artist_id else [])
    elif seed_type == "album":
        album = await deezer.get_album(seed_deezer_id)
        artist_id = (album.get("artist") or {}).get("id") if album else None
        raw = (await deezer.get_artist_radio(artist_id, limit=count + 10)
               if artist_id else [])
    else:
        return []

    seen, out = set(), []
    for t in raw:
        tid = t.get("id")
        if not tid or tid in seen:
            continue
        seen.add(tid)
        norm = {
            "id": tid,
            "title": t.get("title", ""),
            "artist_name": (t.get("artist") or {}).get("name", ""),
            "album_id": (t.get("album") or {}).get("id"),
            "album_title": (t.get("album") or {}).get("title", ""),
            "cover_url": (t.get("album") or {}).get("cover_medium", ""),
            "duration": t.get("duration", 0),
        }
        if await library.is_in_library(norm, db):
            continue
        out.append(norm)
        if len(out) >= count:
            break
    return out


async def start_radio(deezer, navidrome, db, downloader, user: dict,
                      seed_type: str, seed_deezer_id: int, seed_title: str,
                      seed_cover_url: Optional[str], track_count: int,
                      ttl_hours: int) -> dict:
    tracks = await get_radio_tracks(deezer, seed_type, seed_deezer_id, track_count, db)
    if not tracks:
        raise ValueError("No radio tracks found for this seed")

    expires = (_dt.datetime.now(_dt.timezone.utc)
               + _dt.timedelta(hours=ttl_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    session_id = await db.create_radio_session(
        user_id=user["id"], seed_type=seed_type, seed_deezer_id=seed_deezer_id,
        seed_title=seed_title, seed_cover_url=seed_cover_url,
        expires_at=expires, track_count=len(tracks))

    name = playlist_name(seed_title)
    playlist_id = None
    user_auth = auth.user_subsonic_auth(user)
    if user_auth:
        try:
            playlist_id = await navidrome.create_playlist(name, user_auth)
        except Exception as exc:
            log.warning("radio playlist create failed: %s", exc)
    await db.update_radio_session(session_id, navidrome_playlist_id=playlist_id,
                                  navidrome_playlist_name=name)

    for t in tracks:
        dl_id = await downloader.enqueue(
            "deezer", deezer_type="track", deezer_id=t["id"],
            title=t["title"], artist=t["artist_name"], cover_url=t["cover_url"],
            requested_by=user["id"], radio_session_id=session_id)
        await db.add_radio_track(
            session_id, t["id"], deezer_album_id=t.get("album_id"),
            title=t["title"], artist=t["artist_name"], album=t.get("album_title"),
            cover_url=t.get("cover_url"), download_id=dl_id, status="pending")

    return {
        "session_id": session_id,
        "playlist_name": name,
        "track_count": len(tracks),
        "tracks_ready": 0,
        "expires_at": expires,
    }


async def like_radio_track(db, navidrome, telegram, music_dir: str,
                           session_id: str, deezer_track_id: int) -> str:
    rt = await db.get_radio_track(session_id, deezer_track_id)
    if not rt:
        raise ValueError("radio track not found")
    if rt["status"] != "ready":
        raise ValueError(f"track not ready (status={rt['status']})")

    src = rt["file_path"]
    artist = _sanitize(rt.get("artist") or "Unknown Artist")
    album = _sanitize(rt.get("album") or "Singles")
    filename = os.path.basename(src)
    dest_dir = os.path.join(music_dir, artist, album)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, filename)

    await asyncio.to_thread(shutil.move, src, dest)
    rel = os.path.relpath(dest, music_dir)

    await db.update_radio_track(rt["id"], status="liked", file_path=dest,
                                rel_path=rel, liked_at=_now())

    tags = await asyncio.to_thread(library._read_tags, dest, rel)
    await db.upsert_library_track(
        file_path=rel, deezer_id=deezer_track_id,
        deezer_album_id=rt.get("deezer_album_id"),
        is_pinned=1, location="local", **tags)

    if telegram:
        async def cb(msg_id, file_id):
            await db.set_telegram_backed(rel, msg_id, file_id)
            await db.add_telegram_file(rel, msg_id, file_id, tags.get("file_size_mb"))
        telegram.enqueue_upload(dest, rel, cb)

    await navidrome.trigger_scan()
    return rel


async def dismiss_session(db, navidrome, music_dir: str, session_id: str) -> None:
    session = await db.get_radio_session(session_id)
    if not session:
        return
    tracks = await db.list_active_radio_tracks(session_id)
    for rt in tracks:
        fp = rt.get("file_path")
        if fp and os.path.isfile(fp):
            try:
                await asyncio.to_thread(os.remove, fp)
            except OSError as exc:
                log.warning("radio cleanup: could not remove %s: %s", fp, exc)
        await db.update_radio_track(rt["id"], status="deleted")

    sess_dir = os.path.join(music_dir, "radio", session_id)
    try:
        await asyncio.to_thread(shutil.rmtree, sess_dir, ignore_errors=True)
    except Exception as exc:
        log.warning("radio cleanup: rmtree %s failed: %s", sess_dir, exc)

    playlist_id = session.get("navidrome_playlist_id")
    if playlist_id:
        user = await db.get_user_by_id(session["user_id"])
        user_auth = auth.user_subsonic_auth(user) if user else None
        if user_auth:
            try:
                await navidrome.delete_playlist(playlist_id, user_auth)
            except Exception as exc:
                log.warning("radio playlist delete failed: %s", exc)

    await db.dismiss_radio_session(session_id)
    await navidrome.trigger_scan()


async def cleanup_loop(db, navidrome, music_dir: str, interval: int = 900) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            for s in await db.get_expired_active_sessions():
                try:
                    await dismiss_session(db, navidrome, music_dir, s["id"])
                    log.info("radio: expired session %s cleaned up", s["id"])
                except Exception as exc:
                    log.error("radio cleanup failed for %s: %s", s["id"], exc)
        except Exception as exc:
            log.error("radio cleanup loop error: %s", exc)
