"""
downloader.py — SQLite-backed async download worker (deemix + yt-dlp).

A single asyncio worker pulls the oldest 'pending' row from the `downloads`
table and fetches it: deemix for Deezer, the yt_dlp Python API for YouTube.
After each *permanent* (non-radio) success the file is indexed into
library_tracks, Navidrome is asked to rescan, and the file is enqueued for
Telegram cold-storage backup. Radio downloads land in /music/radio/<session>/,
are added to the session's Navidrome playlist, and are NOT backed up.

deemix specifics carried over from the MVP:
  • config.json written with fallbackBitrate=true so a too-high bitrate request
    steps down (320→128) instead of silently downloading nothing.
  • ARL validated at startup via deezer-py and logged loudly.

Interrupted ('downloading') rows are reset to 'pending' on startup and retried;
deemix's overwriteFile='n' makes re-running a partial download safe.
"""

import asyncio
import datetime as _dt
import json
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

import library

log = logging.getLogger("downloader")

_POLL_INTERVAL = 5.0
_ERR_TAIL = 500

_FAILURE_MARKERS = (
    "track not found", "not available", "no tracks", "isn't available",
    "can't be", "error downloading", "track token", "wrong license",
)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Downloader:
    def __init__(
        self,
        arl: str,
        music_dir: str,
        navidrome,
        db,
        telegram=None,
        config_dir: str = "/root/.config/deemix",
        bitrate: Optional[str] = None,
        http=None,
    ):
        self.arl        = arl
        self.music_dir  = Path(music_dir)
        self.config_dir = Path(config_dir)
        self.navidrome  = navidrome
        self.db         = db
        self.telegram   = telegram
        self.http       = http
        self.bitrate    = (bitrate or os.environ.get("DEEMIX_BITRATE", "320")).lower()
        self.arl_ok: Optional[bool] = None
        self._wake = asyncio.Event()
        self._worker_task: Optional[asyncio.Task] = None
        self._configure()

    # ── deemix config ───────────────────────────────────────────────────────

    def _configure(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.config_dir / ".arl").write_text(self.arl.strip())

        cfg_file = self.config_dir / "config.json"
        cfg: dict = {}
        if cfg_file.is_file():
            try:
                cfg = json.loads(cfg_file.read_text() or "{}")
            except Exception as exc:
                log.warning("existing deemix config.json unreadable, rewriting: %s", exc)
                cfg = {}
        cfg.update({
            "downloadLocation":   str(self.music_dir),
            "fallbackBitrate":    True,
            "fallbackSearch":     True,
            "overwriteFile":      "n",
            "createArtistFolder": True,
            "createAlbumFolder":  True,
            # Cover art: embed into the file *and* drop a folder cover.jpg so
            # Navidrome/Symfonium always have art to show. (Explicit rather than
            # relying on deemix defaults.)
            "saveArtwork":        True,
            "embeddedArtworkSize": 800,
            "coverImageTemplate": "cover",
        })
        cfg_file.write_text(json.dumps(cfg, indent=2))
        self.music_dir.mkdir(parents=True, exist_ok=True)
        log.info("deemix config dir: %s (bitrate=%s, fallback on)",
                 self.config_dir, self.bitrate)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        await self._validate_arl()
        resumed = await self.db.reset_interrupted_downloads()
        if resumed:
            log.info("reset %d interrupted download(s) back to pending", resumed)
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker())
            log.info("download worker started")
        self._wake.set()

    async def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

    def _check_arl_sync(self) -> bool:
        from deezer import Deezer
        dz = Deezer()
        try:
            return bool(dz.login_via_arl(self.arl.strip()))
        except Exception as exc:
            log.warning("ARL validation raised: %s", exc)
            return False

    async def _validate_arl(self) -> None:
        try:
            self.arl_ok = await asyncio.to_thread(self._check_arl_sync)
        except Exception as exc:
            self.arl_ok = False
            log.warning("ARL validation error: %s", exc)
        if self.arl_ok:
            log.info("Deezer ARL OK — downloads enabled")
        else:
            log.error("Deezer ARL INVALID or expired — downloads will fail. "
                      "Refresh DEEZER_ARL and restart the gateway.")

    def wake(self) -> None:
        self._wake.set()

    # ── public enqueue (used by main.py routes) ──────────────────────────────

    async def enqueue(self, source: str, *, deezer_type=None, deezer_id=None,
                      yt_id=None, yt_query=None, title=None, artist=None,
                      cover_url=None, requested_by=None,
                      radio_session_id=None) -> int:
        if source == "deezer":
            if deezer_type == "track":
                url = f"https://www.deezer.com/track/{deezer_id}"
            elif deezer_type == "album":
                url = f"https://www.deezer.com/album/{deezer_id}"
            else:
                raise ValueError("deezer download needs type track|album")
        elif source == "youtube":
            url = f"https://www.youtube.com/watch?v={yt_id}"
        else:
            raise ValueError(f"unsupported source {source!r}")

        dl_id = await self.db.add_download(
            source=source, url=url, deezer_type=deezer_type, deezer_id=deezer_id,
            yt_query=yt_query or (yt_id if source == "youtube" else None),
            title=title, artist=artist, cover_url=cover_url,
            requested_by=requested_by, bitrate_requested=self.bitrate,
            radio_session_id=radio_session_id,
        )
        self._wake.set()
        log.info("queued %s download id=%d", source, dl_id)
        return dl_id

    # ── worker ────────────────────────────────────────────────────────────────

    async def _worker(self) -> None:
        while True:
            try:
                job = await self.db.get_oldest_pending()
            except Exception as exc:
                log.error("queue read failed: %s", exc)
                job = None

            if job is not None:
                try:
                    await self._process(job)
                except Exception as exc:
                    log.error("download worker error for id=%s: %s", job.get("id"), exc)
                continue

            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=_POLL_INTERVAL)
            except asyncio.TimeoutError:
                pass

    async def _process(self, job: dict) -> None:
        dl_id = job["id"]
        is_radio = bool(job.get("radio_session_id"))
        dest = self.music_dir
        if is_radio:
            dest = self.music_dir / "radio" / job["radio_session_id"]
            dest.mkdir(parents=True, exist_ok=True)

        await self.db.update_download_status(dl_id, "downloading", started_at=_now())

        before = _snapshot(dest)
        try:
            if job["source"] == "deezer":
                ok, output = await self._run_deemix(job["url"], dest)
            elif job["source"] == "youtube":
                ok, output = await self._run_ytdlp(job, dest)
            else:
                ok, output = False, f"unknown source {job['source']}"
        except Exception as exc:
            ok, output = False, f"download crashed: {exc}"

        if not ok:
            await self.db.update_download_status(
                dl_id, "error", error_msg=output[-_ERR_TAIL:], finished_at=_now())
            return

        new_files = _new_files(dest, before)
        if not new_files:
            await self.db.update_download_status(
                dl_id, "error", error_msg="no new files produced\n" + output[-_ERR_TAIL:],
                finished_at=_now())
            return

        primary = new_files[0]
        rel_primary = os.path.relpath(primary, self.music_dir)
        tags = await asyncio.to_thread(library._read_tags, primary, rel_primary)

        await self.db.update_download_status(
            dl_id, "done",
            file_path=rel_primary,
            file_size_mb=tags.get("file_size_mb"),
            bitrate_actual=str(tags.get("bitrate_kbps") or ""),
            finished_at=_now(),
        )

        if is_radio:
            await self._finish_radio(job, primary, rel_primary, tags)
        else:
            await self._finish_permanent(job, new_files)

    async def _finish_permanent(self, job: dict, new_files: list[str]) -> None:
        is_track = job.get("deezer_type") == "track"
        for path in new_files:
            rel = os.path.relpath(path, self.music_dir)
            tags = await asyncio.to_thread(library._read_tags, path, rel)
            await self.db.upsert_library_track(
                file_path=rel, deezer_id=job.get("deezer_id"),
                deezer_album_id=(job.get("deezer_id") if job.get("deezer_type") == "album" else None),
                location="local", **tags,
            )
            await self._write_lyrics_sidecar(path, tags, is_track, job)
        await self.navidrome.trigger_scan()
        if self.telegram:
            for path in new_files:
                rel = os.path.relpath(path, self.music_dir)
                self.telegram.enqueue_upload(path, rel, self._make_tg_callback(rel, job["id"]))

    async def _finish_radio(self, job: dict, primary: str, rel: str, tags: dict) -> None:
        sid = job["radio_session_id"]
        rt = await self.db.get_radio_track_by_download(job["id"])
        if rt:
            await self.db.update_radio_track(
                rt["id"], status="ready", file_path=primary, rel_path=rel)
        await self.db.increment_radio_tracks_ready(sid)

        # Add to the session's Navidrome playlist (per-user auth).
        try:
            session = await self.db.get_radio_session(sid)
            playlist_id = session.get("navidrome_playlist_id") if session else None
            user = await self.db.get_user_by_id(session["user_id"]) if session else None
            if playlist_id and user:
                import auth
                user_auth = auth.user_subsonic_auth(user)
                if user_auth:
                    # Resolve Navidrome's own song id, then add it.
                    title = tags.get("title") or job.get("title") or ""
                    artist = tags.get("artist") or job.get("artist") or ""
                    sid_song = await self.navidrome.resolve_song_id(title, artist, user_auth)
                    if sid_song:
                        await self.navidrome.add_songs_to_playlist(
                            playlist_id, [sid_song], user_auth)
        except Exception as exc:
            log.warning("radio playlist add failed (session=%s): %s", sid, exc)
        # No Telegram upload, no per-track scan (batched on dismiss/completion).

    async def _write_lyrics_sidecar(self, path: str, tags: dict,
                                    is_track: bool, job: dict) -> None:
        """Best-effort: write a synced .lrc next to the file so Navidrome shows
        lyrics in Symfonium. Never blocks or fails the download."""
        if self.http is None:
            return
        try:
            import lyrics as lyrics_mod
            if not lyrics_mod.is_enabled():
                return
            # Only a real per-track Deezer id is a valid lyrics-cache key; album
            # downloads carry the album id, so don't use it as a track key.
            dz_track_id = job.get("deezer_id") if is_track else 0
            lrc = await lyrics_mod.get_synced_lrc(
                self.http, self.db, dz_track_id or 0,
                tags.get("title") or "", tags.get("artist") or "",
                tags.get("album"), tags.get("duration_sec"))
            if lrc:
                await asyncio.to_thread(lyrics_mod.write_lrc_sidecar, path, lrc)
        except Exception as exc:
            log.warning("lyrics sidecar failed for %s: %s",
                        os.path.relpath(path, self.music_dir), exc)

    def _make_tg_callback(self, rel_path: str, download_id: int):
        async def cb(msg_id: int, file_id: str) -> None:
            try:
                tags_size = None
                lib = await self.db.get_library_track_by_path(rel_path)
                if lib:
                    tags_size = lib.get("file_size_mb")
                await self.db.set_telegram_backed(rel_path, msg_id, file_id)
                await self.db.add_telegram_file(rel_path, msg_id, file_id, tags_size)
                await self.db.update_download_status(
                    download_id, "done", telegram_status="uploaded",
                    telegram_msg_id=msg_id, telegram_file_id=file_id)
            except Exception as exc:
                log.error("telegram callback persist failed for %s: %s", rel_path, exc)
        return cb

    # ── runners ─────────────────────────────────────────────────────────────

    async def _run_deemix(self, url: str, dest: Path) -> Tuple[bool, str]:
        log.info("deemix %s -> %s (bitrate=%s)", url, dest, self.bitrate)
        try:
            proc = await asyncio.create_subprocess_exec(
                "deemix", "--bitrate", self.bitrate, "--path", str(dest), url,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL, cwd=str(dest),
                env={**os.environ, "PYTHONPATH": ""},
            )
            out_bytes, _ = await proc.communicate()
            out = out_bytes.decode(errors="replace")
        except FileNotFoundError:
            return False, "deemix CLI not found"
        except Exception as exc:
            return False, f"download failed: {exc}"

        if proc.returncode != 0:
            return False, f"deemix exited {proc.returncode}\n{out}"
        marker = next((m for m in _FAILURE_MARKERS if m in out.lower()), None)
        if marker:
            return False, f"download did not complete (marker: {marker})\n{out}"
        return True, out

    async def _run_ytdlp(self, job: dict, dest: Path) -> Tuple[bool, str]:
        import ytdlp
        yt_id = job.get("yt_query")
        if not yt_id:
            return False, "missing youtube id"
        try:
            path = await ytdlp.download_track(
                yt_id, str(dest), job.get("artist") or "Unknown Artist",
                album=None)
            return True, f"downloaded {path}"
        except Exception as exc:
            return False, f"yt-dlp failed: {exc}"


def _snapshot(root: Path) -> dict:
    snap = {}
    if not root.is_dir():
        return snap
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.lower().endswith(library.AUDIO_EXTS):
                p = os.path.join(dirpath, f)
                try:
                    snap[p] = os.path.getmtime(p)
                except OSError:
                    pass
    return snap


def _new_files(root: Path, before: dict) -> list[str]:
    after = _snapshot(root)
    new = [p for p, m in after.items() if p not in before or before[p] != m]
    new.sort()
    return new
