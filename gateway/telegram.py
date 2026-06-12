"""
telegram.py — cold-storage backup via the raw Telegram Bot API (httpx only).

Every permanent download is uploaded to a private Telegram channel as an audio
message; the (message_id, file_id) pair is recorded so the file can later be
deleted from the local hot cache and recalled on demand.

A single background worker drains an asyncio.Queue at strictly ≤ 1 upload per
2 seconds — Telegram bans bots that exceed its send rate. Callers never touch
the network directly; they enqueue_upload(...) and supply an on-complete
callback that persists the resulting ids.
"""

import asyncio
import json
import logging
import os
from typing import Awaitable, Callable, Optional, Tuple

import httpx

log = logging.getLogger("telegram")

_UPLOAD_INTERVAL = 2.0   # seconds between uploads (Telegram rate limit)
_INBOUND_TIMEOUT = 30    # getUpdates long-poll seconds
_INBOUND_BACKOFF = 5     # seconds to wait after an error

UploadCallback = Callable[[int, str], Awaitable[None]]


class TelegramClient:
    def __init__(self, http: httpx.AsyncClient, token: str, channel_id: str):
        self.http = http
        self.token = token
        self.channel_id = channel_id
        self._api = f"https://api.telegram.org/bot{token}"
        self._file_base = f"https://api.telegram.org/file/bot{token}"
        self._queue: "asyncio.Queue[tuple[str, str, Optional[UploadCallback]]]" = asyncio.Queue()
        self._worker: Optional[asyncio.Task] = None
        self._inbound: Optional[asyncio.Task] = None

    # ── lifecycle ───────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._uploader_loop())
            log.info("telegram upload worker started")

    async def stop(self) -> None:
        for attr in ("_worker", "_inbound"):
            task = getattr(self, attr)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                setattr(self, attr, None)

    # ── primitives ────────────────────────────────────────────────────────────

    async def test_connection(self) -> bool:
        try:
            r = await self.http.get(f"{self._api}/getMe", timeout=10.0)
            return r.status_code == 200 and r.json().get("ok", False)
        except Exception as exc:
            log.warning("telegram getMe failed: %s", exc)
            return False

    async def upload_file(self, local_path: str, caption: str) -> Tuple[int, str]:
        """Upload one audio file via sendAudio. Returns (message_id, file_id)."""
        filename = os.path.basename(local_path)
        with open(local_path, "rb") as fh:
            files = {"audio": (filename, fh, "audio/mpeg")}
            data = {"chat_id": self.channel_id, "caption": caption[:1024]}
            r = await self.http.post(f"{self._api}/sendAudio", data=data,
                                     files=files, timeout=300.0)
        r.raise_for_status()
        payload = r.json()
        if not payload.get("ok"):
            raise RuntimeError(f"sendAudio failed: {payload}")
        result = payload["result"]
        msg_id = result["message_id"]
        audio = result.get("audio") or result.get("document") or {}
        file_id = audio.get("file_id", "")
        return msg_id, file_id

    async def download_file(self, file_id: str, dest_path: str) -> None:
        r = await self.http.get(f"{self._api}/getFile",
                                params={"file_id": file_id}, timeout=30.0)
        r.raise_for_status()
        tg_path = r.json()["result"]["file_path"]
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        async with self.http.stream("GET", f"{self._file_base}/{tg_path}",
                                    timeout=300.0) as resp:
            resp.raise_for_status()
            with open(dest_path, "wb") as fh:
                async for chunk in resp.aiter_bytes():
                    fh.write(chunk)

    async def send_message(self, chat_id, text: str) -> None:
        """Best-effort plain-text reply (used to confirm DM imports)."""
        try:
            await self.http.post(f"{self._api}/sendMessage",
                                 data={"chat_id": chat_id, "text": text[:4000]},
                                 timeout=15.0)
        except Exception as exc:
            log.warning("telegram sendMessage failed: %s", exc)

    async def delete_message(self, msg_id: int) -> bool:
        try:
            r = await self.http.post(f"{self._api}/deleteMessage",
                                     data={"chat_id": self.channel_id,
                                           "message_id": msg_id}, timeout=15.0)
            return r.status_code == 200 and r.json().get("ok", False)
        except Exception as exc:
            log.warning("telegram deleteMessage %s failed: %s", msg_id, exc)
            return False

    # ── upload queue ────────────────────────────────────────────────────────

    def enqueue_upload(self, local_path: str, caption: str,
                       on_complete: Optional[UploadCallback] = None) -> None:
        self._queue.put_nowait((local_path, caption, on_complete))

    def pending_uploads(self) -> int:
        return self._queue.qsize()

    async def _uploader_loop(self) -> None:
        while True:
            local_path, caption, cb = await self._queue.get()
            try:
                if not os.path.isfile(local_path):
                    log.warning("telegram: file gone before upload: %s", local_path)
                else:
                    msg_id, file_id = await self.upload_file(local_path, caption)
                    if cb:
                        await cb(msg_id, file_id)
                    log.info("telegram: uploaded %s (msg=%s)", caption, msg_id)
            except Exception as exc:
                log.error("telegram upload failed for %s: %s", caption, exc)
            finally:
                self._queue.task_done()
            await asyncio.sleep(_UPLOAD_INTERVAL)

    # ── inbound ingest (getUpdates long-poll) ────────────────────────────────

    AudioHandler = Callable[[dict, dict], Awaitable[None]]

    def start_inbound(self, on_audio: "TelegramClient.AudioHandler",
                      get_offset: Callable[[], Awaitable[int]],
                      set_offset: Callable[[int], Awaitable[None]]) -> None:
        """Start watching the channel for incoming audio. `on_audio(audio, msg)`
        is awaited for each audio message; offset is persisted via the getters
        so restarts don't reprocess."""
        if self._inbound is None:
            self._inbound = asyncio.create_task(
                self._inbound_loop(on_audio, get_offset, set_offset))
            log.info("telegram inbound worker started")

    @staticmethod
    def _extract_audio(msg: dict) -> Optional[dict]:
        """Pull audio info from a message, or None if it carries no audio."""
        sender = msg.get("from") or {}
        from_bot = bool(sender.get("is_bot"))
        audio = msg.get("audio")
        if audio and audio.get("file_id"):
            return {
                "file_id": audio["file_id"],
                "performer": audio.get("performer"),
                "title": audio.get("title"),
                "file_name": audio.get("file_name"),
                "mime": audio.get("mime_type"),
                "file_size": audio.get("file_size"),
                "from_bot": from_bot,
            }
        doc = msg.get("document")
        if doc and (doc.get("mime_type") or "").startswith("audio/"):
            return {
                "file_id": doc["file_id"],
                "performer": None,
                "title": None,
                "file_name": doc.get("file_name"),
                "mime": doc.get("mime_type"),
                "file_size": doc.get("file_size"),
                "from_bot": from_bot,
            }
        return None

    async def _maybe_help_reply(self, msg: dict) -> None:
        """Reply to a /start or stray text in a private chat so the user knows
        how to use the bot. Ignored for channel posts and non-text messages."""
        chat = msg.get("chat") or {}
        if chat.get("type") != "private":
            return
        text = (msg.get("text") or "").strip()
        if not text:
            return
        await self.send_message(
            chat.get("id"),
            "🎵 Send or forward an audio file here and I'll add it to the music "
            "library. (Max ~20 MB per file.)")

    async def _inbound_loop(self, on_audio, get_offset, set_offset) -> None:
        offset = await get_offset()
        while True:
            try:
                params = {
                    "timeout": _INBOUND_TIMEOUT,
                    "allowed_updates": json.dumps(["channel_post", "message"]),
                }
                if offset:
                    params["offset"] = offset
                r = await self.http.get(f"{self._api}/getUpdates", params=params,
                                        timeout=_INBOUND_TIMEOUT + 10)
                data = r.json()
                if not data.get("ok"):
                    log.warning("telegram getUpdates not ok: %s", data)
                    await asyncio.sleep(_INBOUND_BACKOFF)
                    continue
                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    msg = upd.get("channel_post") or upd.get("message")
                    if msg:
                        audio = self._extract_audio(msg)
                        if audio:
                            try:
                                await on_audio(audio, msg)
                            except Exception as exc:
                                log.error("telegram inbound handler failed: %s", exc)
                        else:
                            await self._maybe_help_reply(msg)
                    await set_offset(offset)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("telegram getUpdates error: %s", exc)
                await asyncio.sleep(_INBOUND_BACKOFF)
