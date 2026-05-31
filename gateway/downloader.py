"""
downloader.py — async background download queue using deemix, backed by SQLite.

A single asyncio worker pulls the oldest 'pending' row from the `downloads`
table (see db.py) and shells out to the `deemix` CLI to fetch it. After each
successful download we ask Navidrome to rescan so the new file shows up quickly.

Why SQLite instead of an in-memory asyncio.Queue: pending downloads now survive
a restart. On startup any row left 'downloading' (interrupted mid-fetch) is reset
to 'pending' and retried — deemix's overwriteFile='n' makes re-running a partial
download safe.

Two things make downloads actually work here that didn't with deemix's defaults:

  1. We write deemix's config.json with **fallbackBitrate = true**. deemix
     defaults it to false, so requesting a bitrate the account can't serve
     (e.g. FLAC/320 on a Free/standard account) downloaded *nothing*, silently.
     With fallback on, deemix steps down (320 → 128) instead. The default
     request bitrate is configurable via DEEMIX_BITRATE.

  2. We validate the ARL at startup with deezer-py and log the result loudly,
     so an expired/invalid ARL is obvious in `docker compose logs` instead of
     surfacing as a cryptic EOFError mid-download.

The ARL is written to deemix's config dir (.arl) on startup; the config folder
is also where config.json lives.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger("downloader")

# How often the worker re-checks the DB when idle, if no wake-up arrives first.
_POLL_INTERVAL = 2.0

# How many characters of deemix output to keep as the error_msg on failure.
_ERR_TAIL = 500

# Substrings in deemix output that mean a track didn't actually come down,
# even though the CLI may still exit 0.
_FAILURE_MARKERS = (
    "track not found", "not available", "no tracks", "isn't available",
    "can't be", "error downloading", "track token", "wrong license",
)


class Downloader:
    def __init__(
        self,
        arl: str,
        music_dir: str,
        navidrome,                                  # NavidromeClient (for rescan)
        db,                                         # db.Database (SQLite-backed queue)
        config_dir: str = "/root/.config/deemix",
        bitrate: Optional[str] = None,              # FLAC, 320, 128 (env override)
    ):
        self.arl        = arl
        self.music_dir  = Path(music_dir)
        self.config_dir = Path(config_dir)
        self.navidrome  = navidrome
        self.db         = db
        # Default to 320 (degrades to 128 via fallback); HiFi accounts can
        # set DEEMIX_BITRATE=FLAC. deemix parses these case-insensitively.
        self.bitrate    = (bitrate or os.environ.get("DEEMIX_BITRATE", "320")).lower()
        self.arl_ok: Optional[bool] = None
        self._wake = asyncio.Event()                # set() to wake the worker now
        self._worker_task: Optional[asyncio.Task] = None
        self._configure()

    # ── config ────────────────────────────────────────────────────────────────

    def _configure(self) -> None:
        """Write the ARL + a deemix config.json that enables bitrate fallback."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

        arl_file = self.config_dir / ".arl"
        arl_file.write_text(self.arl.strip())

        # Merge our critical overrides into any existing config.json so deemix
        # never falls back to its (download-breaking) defaults. deemix fills in
        # every other key from its own DEFAULTS on load.
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
            "fallbackBitrate":    True,   # ← the fix: step down instead of failing
            "fallbackSearch":     True,   # find an alternate source if the exact id fails
            "overwriteFile":      "n",    # don't redownload existing files
            "createArtistFolder": True,
            "createAlbumFolder":  True,
        })
        cfg_file.write_text(json.dumps(cfg, indent=2))

        self.music_dir.mkdir(parents=True, exist_ok=True)
        log.info("deemix config dir: %s (ARL + config.json written, bitrate=%s, fallback on)",
                 self.config_dir, self.bitrate)

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        await self._validate_arl()

        # Recover anything interrupted by the previous restart, then start the
        # worker. It will immediately pick up all pre-existing 'pending' rows.
        resumed = await self.db.reset_stuck_downloads()
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
        # Imported lazily and by package name. After the deezer.py → deezer_api.py
        # rename there is no local module to shadow this `deezer-py` import.
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
            log.error(
                "Deezer ARL INVALID or expired — downloads will fail. "
                "Refresh DEEZER_ARL in your .env (log into Deezer in a browser, "
                "copy the `arl` cookie) and restart the gateway."
            )

    # ── public API ────────────────────────────────────────────────────────────

    async def enqueue(
        self,
        type: str,
        deezer_id: int,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        cover_url: Optional[str] = None,
    ) -> int:
        """Persist a new download to the queue and wake the worker. Returns row id."""
        if type == "track":
            url = f"https://www.deezer.com/track/{deezer_id}"
        elif type == "album":
            url = f"https://www.deezer.com/album/{deezer_id}"
        else:
            raise ValueError(f"unsupported download type: {type!r}")

        dl_id = await self.db.add_download(type, deezer_id, url, title, artist, cover_url)
        self._wake.set()
        log.info("queued %s download id=%d deezer_id=%s", type, dl_id, deezer_id)
        return dl_id

    # ── worker ────────────────────────────────────────────────────────────────

    async def _worker(self) -> None:
        while True:
            try:
                row = await self.db.next_pending()
            except Exception as exc:
                log.error("queue read failed: %s", exc)
                row = None

            if row is not None:
                try:
                    await self._process(row)
                except Exception as exc:
                    log.error("download worker error for id=%s: %s", row.get("id"), exc)
                continue

            # Idle: wait for a wake-up (new enqueue) or fall back to a poll.
            # The poll guarantees correctness even if a wake-up is ever missed.
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=_POLL_INTERVAL)
            except asyncio.TimeoutError:
                pass

    async def _process(self, row: dict) -> None:
        dl_id = row["id"]
        url   = row["url"]
        await self.db.set_download_status(dl_id, "downloading")

        ok, output = await self._download(url)

        if ok:
            await self.db.set_download_status(dl_id, "done")
            await self.navidrome.trigger_scan()
        else:
            await self.db.set_download_status(dl_id, "error", error_msg=output[-_ERR_TAIL:])

    async def _download(self, url: str) -> Tuple[bool, str]:
        """Run deemix for one URL. Returns (success, output-or-error-message)."""
        log.info("downloading %s (bitrate=%s)", url, self.bitrate)
        try:
            proc = await asyncio.create_subprocess_exec(
                "deemix",
                "--bitrate", self.bitrate,
                "--path", str(self.music_dir),
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL,    # never block on interactive prompts
                cwd=str(self.music_dir),             # neutral cwd: nothing here shadows `deezer`
                env={**os.environ, "PYTHONPATH": ""},  # don't put /app on the child's path
            )
            out_bytes, _ = await proc.communicate()
            out = out_bytes.decode(errors="replace")
        except FileNotFoundError:
            log.error("deemix CLI not found — is it installed in the container?")
            return False, "deemix CLI not found"
        except Exception as exc:
            log.error("download failed for %s: %s", url, exc)
            return False, f"download failed: {exc}"

        if proc.returncode != 0:
            log.error("deemix exit %d for %s:\n%s", proc.returncode, url, out[-1500:])
            return False, f"deemix exited {proc.returncode}\n{out}"

        lowered = out.lower()
        marker  = next((m for m in _FAILURE_MARKERS if m in lowered), None)
        if marker:
            log.warning("deemix finished but the track may not have downloaded "
                        "(%s, marker=%r). Tail:\n%s", url, marker, out[-1500:])
            return False, f"download did not complete (marker: {marker})\n{out}"

        log.info("downloaded: %s", url)
        return True, out
