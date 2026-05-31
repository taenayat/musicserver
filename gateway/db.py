"""
db.py — SQLite persistence for the download queue (via aiosqlite).

Replaces the old in-memory asyncio.Queue so that pending downloads survive a
gateway restart. A single shared connection is used; aiosqlite serialises all
statements onto one background thread, which is plenty for this low-traffic,
single-user service.

Schema
------
downloads : one row per queued track/album download, with lifecycle status.
settings  : tiny key/value store for misc state (unused by the MVP routes but
            specified, and handy for things like "last_scan_at").

`init_db(db_path)` returns a ready `Database` instance. main.py holds it for the
lifetime of the app and hands the same instance to the Downloader.
"""

import datetime as _dt
from typing import Any, Optional

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS downloads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    deezer_type TEXT    NOT NULL,
    deezer_id   INTEGER NOT NULL,
    url         TEXT    NOT NULL,
    status      TEXT    NOT NULL,
    title       TEXT,
    artist      TEXT,
    cover_url   TEXT,
    queued_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    error_msg   TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_downloads_status    ON downloads(status);
CREATE INDEX IF NOT EXISTS idx_downloads_queued_at ON downloads(queued_at DESC);
"""

# Status values are a small closed set; centralised so callers can validate.
STATUSES = ("pending", "downloading", "done", "error")


def _iso(ts: Optional[str]) -> Optional[str]:
    """
    Normalise a SQLite CURRENT_TIMESTAMP ("YYYY-MM-DD HH:MM:SS", UTC) into an
    ISO-8601 string the browser can parse unambiguously ("...THH:MM:SSZ").
    Pass-through if it already looks ISO or is NULL.
    """
    if not ts:
        return None
    if "T" in ts:
        return ts
    return ts.replace(" ", "T") + "Z"


def _row_to_item(row: aiosqlite.Row) -> dict:
    """Map a downloads row to the API queue-item shape (deezer_type → type)."""
    return {
        "id":          row["id"],
        "type":        row["deezer_type"],
        "deezer_id":   row["deezer_id"],
        "title":       row["title"],
        "artist":      row["artist"],
        "cover_url":   row["cover_url"],
        "status":      row["status"],
        "queued_at":   _iso(row["queued_at"]),
        "finished_at": _iso(row["finished_at"]),
        "error_msg":   row["error_msg"],
    }


class Database:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    # ── lifecycle ──────────────────────────────────────────────────────────────

    @classmethod
    async def connect(cls, db_path: str) -> "Database":
        conn = await aiosqlite.connect(db_path)
        conn.row_factory = aiosqlite.Row
        # WAL + a busy timeout keep the worker and request handlers from
        # tripping over each other on the single file.
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA busy_timeout=5000;")
        await conn.executescript(_SCHEMA)
        await conn.commit()
        return cls(conn)

    async def close(self) -> None:
        await self._conn.close()

    # ── downloads ──────────────────────────────────────────────────────────────

    async def add_download(
        self,
        type: str,
        deezer_id: int,
        url: str,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        cover_url: Optional[str] = None,
    ) -> int:
        cur = await self._conn.execute(
            """INSERT INTO downloads
                   (deezer_type, deezer_id, url, status, title, artist, cover_url)
               VALUES (?, ?, ?, 'pending', ?, ?, ?)""",
            (type, deezer_id, url, title, artist, cover_url),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def set_download_status(
        self, id: int, status: str, error_msg: Optional[str] = None
    ) -> None:
        # finished_at is stamped (in the same SQLite format as queued_at) only
        # for terminal states, so a re-queued/resumed row clears it again.
        if status in ("done", "error"):
            await self._conn.execute(
                """UPDATE downloads
                      SET status = ?, error_msg = ?, finished_at = CURRENT_TIMESTAMP
                    WHERE id = ?""",
                (status, error_msg, id),
            )
        else:
            await self._conn.execute(
                """UPDATE downloads
                      SET status = ?, error_msg = ?, finished_at = NULL
                    WHERE id = ?""",
                (status, error_msg, id),
            )
        await self._conn.commit()

    async def get_queue(self, limit: int = 50) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM downloads ORDER BY queued_at DESC, id DESC LIMIT ?",
            (limit,),
        )
        rows = await cur.fetchall()
        return [_row_to_item(r) for r in rows]

    async def get_download(self, id: int) -> Optional[dict]:
        cur = await self._conn.execute("SELECT * FROM downloads WHERE id = ?", (id,))
        row = await cur.fetchone()
        return _row_to_item(row) if row else None

    async def delete_download(self, id: int) -> None:
        await self._conn.execute("DELETE FROM downloads WHERE id = ?", (id,))
        await self._conn.commit()

    async def count_pending(self) -> int:
        cur = await self._conn.execute(
            "SELECT COUNT(*) FROM downloads WHERE status IN ('pending', 'downloading')"
        )
        row = await cur.fetchone()
        return row[0] if row else 0

    # ── worker support ─────────────────────────────────────────────────────────

    async def reset_stuck_downloads(self) -> int:
        """
        On startup, any row still 'downloading' was interrupted by the restart.
        Put it back to 'pending' so the worker re-attempts it. Returns the count.
        """
        cur = await self._conn.execute(
            "UPDATE downloads SET status = 'pending', finished_at = NULL "
            "WHERE status = 'downloading'"
        )
        await self._conn.commit()
        return cur.rowcount

    async def next_pending(self) -> Optional[dict]:
        """
        Oldest pending row (FIFO by queued_at), or None. Returns the *raw* row
        (all columns, incl. `url`) since the worker needs the download URL, not
        the trimmed API shape.
        """
        cur = await self._conn.execute(
            "SELECT * FROM downloads WHERE status = 'pending' "
            "ORDER BY queued_at ASC, id ASC LIMIT 1"
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    # ── settings ───────────────────────────────────────────────────────────────

    async def get_setting(self, key: str) -> Optional[str]:
        cur = await self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        row = await cur.fetchone()
        return row["value"] if row else None

    async def set_setting(self, key: str, value: Any) -> None:
        await self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        await self._conn.commit()


async def init_db(db_path: str) -> Database:
    """Create the schema if needed and return a connected Database handle."""
    return await Database.connect(db_path)
