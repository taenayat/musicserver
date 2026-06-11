"""
db.py — SQLite persistence layer for the Music Gateway (via aiosqlite).

Holds everything: users + sessions (auth), the download queue, the library
index, Telegram backup records, radio sessions/tracks, lyrics cache and
metrics history. A single shared aiosqlite connection serialises all
statements onto one background thread, which is plenty for this low-traffic
service.

`init_db(path)` returns a ready `Database`. main.py holds the instance for the
app lifetime and hands it to every module that needs persistence.

All timestamps are stored UTC. CURRENT_TIMESTAMP columns ("YYYY-MM-DD HH:MM:SS")
are normalised to ISO-8601 (with a trailing Z) on the way out via `_iso`.
"""

import datetime as _dt
import secrets
from typing import Any, Optional

import aiosqlite


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso(ts: Optional[str]) -> Optional[str]:
    """Normalise a SQLite timestamp into an unambiguous ISO-8601 UTC string."""
    if not ts:
        return None
    if "T" in ts:
        return ts if ts.endswith("Z") or "+" in ts else ts + "Z"
    return ts.replace(" ", "T") + "Z"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    navidrome_user  TEXT,
    navidrome_pass  TEXT,
    role            TEXT DEFAULT 'user',
    navidrome_id    TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at  TEXT NOT NULL,
    last_seen   TEXT
);

CREATE TABLE IF NOT EXISTS downloads (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    requested_by      INTEGER REFERENCES users(id),
    source            TEXT NOT NULL,
    deezer_type       TEXT,
    deezer_id         INTEGER,
    yt_query          TEXT,
    url               TEXT NOT NULL,
    status            TEXT DEFAULT 'pending',
    title             TEXT,
    artist            TEXT,
    cover_url         TEXT,
    bitrate_requested TEXT,
    bitrate_actual    TEXT,
    file_path         TEXT,
    file_size_mb      REAL,
    radio_session_id  TEXT,
    queued_at         TEXT DEFAULT CURRENT_TIMESTAMP,
    started_at        TEXT,
    finished_at       TEXT,
    error_msg         TEXT,
    telegram_status   TEXT DEFAULT 'pending',
    telegram_msg_id   INTEGER,
    telegram_file_id  TEXT
);

CREATE TABLE IF NOT EXISTS library_tracks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path       TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    artist          TEXT NOT NULL,
    album           TEXT,
    track_number    INTEGER,
    duration_sec    INTEGER,
    file_size_mb    REAL,
    format          TEXT,
    bitrate_kbps    INTEGER,
    deezer_id       INTEGER,
    deezer_album_id INTEGER,
    fingerprint     TEXT NOT NULL,
    added_at        TEXT DEFAULT CURRENT_TIMESTAMP,
    last_scanned    TEXT,
    telegram_backed INTEGER DEFAULT 0,
    telegram_msg_id INTEGER,
    telegram_file_id TEXT,
    is_pinned       INTEGER DEFAULT 0,
    last_played     TEXT,
    play_count_30d  INTEGER DEFAULT 0,
    location        TEXT DEFAULT 'local'
);

CREATE TABLE IF NOT EXISTS telegram_files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path    TEXT UNIQUE NOT NULL,
    msg_id       INTEGER NOT NULL,
    file_id      TEXT NOT NULL,
    file_size_mb REAL,
    uploaded_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    status       TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS radio_sessions (
    id                      TEXT PRIMARY KEY,
    user_id                 INTEGER REFERENCES users(id) ON DELETE CASCADE,
    seed_type               TEXT NOT NULL,
    seed_deezer_id          INTEGER NOT NULL,
    seed_title              TEXT NOT NULL,
    seed_cover_url          TEXT,
    navidrome_playlist_id   TEXT,
    navidrome_playlist_name TEXT,
    status                  TEXT DEFAULT 'active',
    track_count             INTEGER DEFAULT 0,
    tracks_ready            INTEGER DEFAULT 0,
    created_at              TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS radio_tracks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT REFERENCES radio_sessions(id) ON DELETE CASCADE,
    deezer_track_id INTEGER NOT NULL,
    deezer_album_id INTEGER,
    title           TEXT,
    artist          TEXT,
    album           TEXT,
    cover_url       TEXT,
    file_path       TEXT,
    rel_path        TEXT,
    download_id     INTEGER REFERENCES downloads(id),
    status          TEXT DEFAULT 'pending',
    liked_at        TEXT
);

CREATE TABLE IF NOT EXISTS lyrics_cache (
    deezer_track_id INTEGER PRIMARY KEY,
    synced          TEXT,
    plain           TEXT,
    source          TEXT,
    fetched_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metrics_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at  TEXT NOT NULL,
    cpu_percent  REAL,
    ram_mb       REAL,
    disk_gb      REAL,
    queue_depth  INTEGER,
    active_users INTEGER
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

"""

# Indexes run AFTER the ADD COLUMN migrations below — on a database created by
# the older MVP schema, columns like downloads.radio_session_id don't exist
# until migrated, so an index referencing them must not be in _SCHEMA.
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_library_deezer      ON library_tracks(deezer_id)",
    "CREATE INDEX IF NOT EXISTS idx_library_fp          ON library_tracks(fingerprint)",
    "CREATE INDEX IF NOT EXISTS idx_library_album       ON library_tracks(deezer_album_id)",
    "CREATE INDEX IF NOT EXISTS idx_downloads_status    ON downloads(status)",
    "CREATE INDEX IF NOT EXISTS idx_downloads_queued_at ON downloads(queued_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_downloads_radio     ON downloads(radio_session_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user       ON sessions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_expires    ON sessions(expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_radio_tracks_sess   ON radio_tracks(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_radio_sessions_user ON radio_sessions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_metrics_recorded    ON metrics_history(recorded_at DESC)",
]

# ADD COLUMN migrations for databases created by an earlier (MVP) schema.
# Each runs in its own try/except so a pre-existing column is a no-op.
_MIGRATIONS = [
    "ALTER TABLE downloads ADD COLUMN requested_by INTEGER",
    "ALTER TABLE downloads ADD COLUMN source TEXT NOT NULL DEFAULT 'deezer'",
    "ALTER TABLE downloads ADD COLUMN yt_query TEXT",
    "ALTER TABLE downloads ADD COLUMN started_at TEXT",
    "ALTER TABLE downloads ADD COLUMN bitrate_requested TEXT",
    "ALTER TABLE downloads ADD COLUMN bitrate_actual TEXT",
    "ALTER TABLE downloads ADD COLUMN file_path TEXT",
    "ALTER TABLE downloads ADD COLUMN file_size_mb REAL",
    "ALTER TABLE downloads ADD COLUMN radio_session_id TEXT",
    "ALTER TABLE downloads ADD COLUMN telegram_status TEXT DEFAULT 'pending'",
    "ALTER TABLE downloads ADD COLUMN telegram_msg_id INTEGER",
    "ALTER TABLE downloads ADD COLUMN telegram_file_id TEXT",
    "ALTER TABLE library_tracks ADD COLUMN deezer_album_id INTEGER",
]


class Database:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    # ── lifecycle ───────────────────────────────────────────────────────────

    @classmethod
    async def connect(cls, db_path: str) -> "Database":
        conn = await aiosqlite.connect(db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA synchronous=NORMAL;")
        await conn.execute("PRAGMA busy_timeout=5000;")
        await conn.executescript(_SCHEMA)
        # Migrations first (add any columns missing on an older MVP database)...
        for stmt in _MIGRATIONS:
            try:
                await conn.execute(stmt)
            except Exception:
                pass
        # ...then indexes, which may reference just-migrated columns.
        for stmt in _INDEXES:
            try:
                await conn.execute(stmt)
            except Exception:
                pass
        await conn.commit()
        return cls(conn)

    async def close(self) -> None:
        await self._conn.close()

    async def execute(self, sql: str, params: tuple = ()):  # escape hatch / tests
        cur = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cur

    # ── users ───────────────────────────────────────────────────────────────

    async def get_user_by_username(self, username: str) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_user_by_id(self, user_id: int) -> Optional[dict]:
        cur = await self._conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def create_user(
        self,
        username: str,
        pw_hash: str,
        role: str = "user",
        nav_user: Optional[str] = None,
        nav_pass_enc: Optional[str] = None,
        nav_id: Optional[str] = None,
    ) -> int:
        cur = await self._conn.execute(
            """INSERT INTO users
                   (username, password_hash, role, navidrome_user,
                    navidrome_pass, navidrome_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (username, pw_hash, role, nav_user, nav_pass_enc, nav_id, _now_iso()),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def update_user_password(
        self, user_id: int, new_hash: str, new_nav_pass_enc: Optional[str]
    ) -> None:
        await self._conn.execute(
            "UPDATE users SET password_hash = ?, navidrome_pass = ? WHERE id = ?",
            (new_hash, new_nav_pass_enc, user_id),
        )
        await self._conn.commit()

    async def update_user_role(self, user_id: int, role: str) -> None:
        await self._conn.execute(
            "UPDATE users SET role = ? WHERE id = ?", (role, user_id)
        )
        await self._conn.commit()

    async def delete_user(self, user_id: int) -> None:
        await self._conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        await self._conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await self._conn.commit()

    async def list_users(self) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM users ORDER BY id ASC"
        )
        return [dict(r) for r in await cur.fetchall()]

    async def count_users(self) -> int:
        cur = await self._conn.execute("SELECT COUNT(*) FROM users")
        row = await cur.fetchone()
        return row[0] if row else 0

    # ── sessions ────────────────────────────────────────────────────────────

    async def create_session(self, user_id: int, ttl_days: int = 30) -> str:
        token = secrets.token_hex(32)
        now = _dt.datetime.now(_dt.timezone.utc)
        expires = now + _dt.timedelta(days=ttl_days)
        await self._conn.execute(
            """INSERT INTO sessions (token, user_id, created_at, expires_at, last_seen)
               VALUES (?, ?, ?, ?, ?)""",
            (token, user_id, now.strftime("%Y-%m-%dT%H:%M:%SZ"),
             expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
             now.strftime("%Y-%m-%dT%H:%M:%SZ")),
        )
        await self._conn.commit()
        return token

    async def get_session(self, token: str) -> Optional[dict]:
        """Return session row if present and unexpired; refresh last_seen."""
        cur = await self._conn.execute(
            "SELECT * FROM sessions WHERE token = ?", (token,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        expires = row["expires_at"]
        if expires and expires < _now_iso():
            await self._conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            await self._conn.commit()
            return None
        await self._conn.execute(
            "UPDATE sessions SET last_seen = ? WHERE token = ?", (_now_iso(), token)
        )
        await self._conn.commit()
        return dict(row)

    async def delete_session(self, token: str) -> None:
        await self._conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        await self._conn.commit()

    async def count_active_sessions(self, window_minutes: int = 5) -> int:
        cutoff = (
            _dt.datetime.now(_dt.timezone.utc)
            - _dt.timedelta(minutes=window_minutes)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        cur = await self._conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM sessions WHERE last_seen >= ?",
            (cutoff,),
        )
        row = await cur.fetchone()
        return row[0] if row else 0

    async def get_user_last_seen(self) -> dict[int, str]:
        cur = await self._conn.execute(
            "SELECT user_id, MAX(last_seen) AS ls FROM sessions GROUP BY user_id"
        )
        return {r["user_id"]: _iso(r["ls"]) for r in await cur.fetchall()}

    # ── downloads ─────────────────────────────────────────────────────────────

    async def add_download(
        self,
        source: str,
        url: str,
        deezer_type: Optional[str] = None,
        deezer_id: Optional[int] = None,
        yt_query: Optional[str] = None,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        cover_url: Optional[str] = None,
        requested_by: Optional[int] = None,
        bitrate_requested: Optional[str] = None,
        radio_session_id: Optional[str] = None,
    ) -> int:
        tg_status = "not_applicable" if radio_session_id else "pending"
        cur = await self._conn.execute(
            """INSERT INTO downloads
                   (requested_by, source, deezer_type, deezer_id, yt_query, url,
                    status, title, artist, cover_url, bitrate_requested,
                    radio_session_id, telegram_status, queued_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)""",
            (requested_by, source, deezer_type, deezer_id, yt_query, url,
             title, artist, cover_url, bitrate_requested, radio_session_id,
             tg_status, _now_iso()),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def update_download_status(self, id: int, status: str, **fields) -> None:
        cols = ["status = ?"]
        vals: list[Any] = [status]
        for k, v in fields.items():
            cols.append(f"{k} = ?")
            vals.append(v)
        vals.append(id)
        await self._conn.execute(
            f"UPDATE downloads SET {', '.join(cols)} WHERE id = ?", tuple(vals)
        )
        await self._conn.commit()

    async def get_oldest_pending(self) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM downloads WHERE status = 'pending' "
            "ORDER BY queued_at ASC, id ASC LIMIT 1"
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def reset_interrupted_downloads(self) -> int:
        cur = await self._conn.execute(
            "UPDATE downloads SET status = 'pending', started_at = NULL "
            "WHERE status = 'downloading'"
        )
        await self._conn.commit()
        return cur.rowcount

    async def get_queue(self, limit: int = 50, offset: int = 0) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM downloads WHERE radio_session_id IS NULL "
            "ORDER BY queued_at DESC, id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [self._download_to_item(r) for r in await cur.fetchall()]

    async def get_download(self, id: int) -> Optional[dict]:
        cur = await self._conn.execute("SELECT * FROM downloads WHERE id = ?", (id,))
        row = await cur.fetchone()
        return self._download_to_item(row) if row else None

    async def delete_download(self, id: int) -> None:
        await self._conn.execute("DELETE FROM downloads WHERE id = ?", (id,))
        await self._conn.commit()

    async def clear_finished_downloads(self) -> int:
        cur = await self._conn.execute(
            "DELETE FROM downloads WHERE status IN ('done','error','skipped_exists') "
            "AND radio_session_id IS NULL"
        )
        await self._conn.commit()
        return cur.rowcount

    async def count_active_downloads(self) -> int:
        cur = await self._conn.execute(
            "SELECT COUNT(*) FROM downloads WHERE status IN ('pending','downloading')"
        )
        row = await cur.fetchone()
        return row[0] if row else 0

    async def count_downloads_by_status(self) -> dict:
        cur = await self._conn.execute(
            "SELECT status, COUNT(*) AS c FROM downloads GROUP BY status"
        )
        return {r["status"]: r["c"] for r in await cur.fetchall()}

    async def count_downloads_today(self, status: str) -> int:
        today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
        cur = await self._conn.execute(
            "SELECT COUNT(*) FROM downloads WHERE status = ? AND finished_at >= ?",
            (status, today),
        )
        row = await cur.fetchone()
        return row[0] if row else 0

    async def downloads_per_day(self, days: int = 7) -> list[dict]:
        cutoff = (
            _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
        ).strftime("%Y-%m-%d")
        cur = await self._conn.execute(
            "SELECT substr(finished_at,1,10) AS day, COUNT(*) AS c "
            "FROM downloads WHERE status = 'done' AND finished_at >= ? "
            "GROUP BY day ORDER BY day ASC",
            (cutoff,),
        )
        return [{"day": r["day"], "count": r["c"]} for r in await cur.fetchall()]

    @staticmethod
    def _download_to_item(row: aiosqlite.Row) -> dict:
        d = dict(row)
        for ts in ("queued_at", "started_at", "finished_at"):
            d[ts] = _iso(d.get(ts))
        # Back-compat alias used by older frontend code.
        d["type"] = d.get("deezer_type")
        return d

    # ── library ─────────────────────────────────────────────────────────────

    async def upsert_library_track(self, **f) -> int:
        """Insert or update a library_tracks row keyed on file_path."""
        f.setdefault("last_scanned", _now_iso())
        cols = list(f.keys())
        placeholders = ", ".join("?" for _ in cols)
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "file_path")
        cur = await self._conn.execute(
            f"""INSERT INTO library_tracks ({', '.join(cols)})
                VALUES ({placeholders})
                ON CONFLICT(file_path) DO UPDATE SET {updates}""",
            tuple(f[c] for c in cols),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def get_library_track(self, id: int) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM library_tracks WHERE id = ?", (id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_library_track_by_deezer_id(self, deezer_id: int) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM library_tracks WHERE deezer_id = ? LIMIT 1", (deezer_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_library_track_by_fingerprint(self, fp: str) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM library_tracks WHERE fingerprint = ? LIMIT 1", (fp,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_library_track_by_path(self, file_path: str) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM library_tracks WHERE file_path = ?", (file_path,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_library_tracks_by_album(self, deezer_album_id: int) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM library_tracks WHERE deezer_album_id = ?",
            (deezer_album_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def list_all_library_tracks(self) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM library_tracks WHERE location != 'telegram' "
            "ORDER BY file_path"
        )
        return [dict(r) for r in await cur.fetchall()]

    async def backfill_deezer_id(self, file_path: str, deezer_id: int,
                                 deezer_album_id: Optional[int] = None) -> None:
        await self._conn.execute(
            "UPDATE library_tracks SET deezer_id = ?, deezer_album_id = COALESCE(?, deezer_album_id) "
            "WHERE file_path = ?",
            (deezer_id, deezer_album_id, file_path),
        )
        await self._conn.commit()

    async def delete_library_track(self, id: int) -> None:
        await self._conn.execute("DELETE FROM library_tracks WHERE id = ?", (id,))
        await self._conn.commit()

    async def delete_library_track_by_path(self, file_path: str) -> None:
        await self._conn.execute(
            "DELETE FROM library_tracks WHERE file_path = ?", (file_path,)
        )
        await self._conn.commit()

    async def library_stats(self) -> dict:
        cur = await self._conn.execute(
            "SELECT COUNT(*) AS tracks, COUNT(DISTINCT artist) AS artists, "
            "COUNT(DISTINCT album) AS albums FROM library_tracks"
        )
        row = await cur.fetchone()
        fmt_cur = await self._conn.execute(
            "SELECT format, COUNT(*) AS c FROM library_tracks GROUP BY format"
        )
        formats = {r["format"] or "unknown": r["c"] for r in await fmt_cur.fetchall()}
        return {
            "total_tracks": row["tracks"],
            "total_artists": row["artists"],
            "total_albums": row["albums"],
            "formats": formats,
        }

    async def get_cache_size_gb(self) -> float:
        cur = await self._conn.execute(
            "SELECT COALESCE(SUM(file_size_mb), 0) FROM library_tracks "
            "WHERE location IN ('local','both')"
        )
        row = await cur.fetchone()
        return round((row[0] or 0) / 1024.0, 4)

    async def get_evictable_tracks(self, policy: str, pin_recent_days: int) -> list[dict]:
        """
        Candidate tracks for eviction, ordered least-valuable first.
        Excludes pinned, radio, recently-played, and not-yet-backed-up tracks.
        """
        cutoff = (
            _dt.datetime.now(_dt.timezone.utc)
            - _dt.timedelta(days=pin_recent_days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        cur = await self._conn.execute(
            "SELECT * FROM library_tracks "
            "WHERE is_pinned = 0 AND location = 'both' "
            "AND file_path NOT LIKE 'radio/%' "
            "AND (last_played IS NULL OR last_played < ?)",
            (cutoff,),
        )
        rows = [dict(r) for r in await cur.fetchall()]

        now_ms = _dt.datetime.now(_dt.timezone.utc).timestamp() * 1000
        thirty_days_ms = 30 * 86400 * 1000

        def last_played_ms(r):
            lp = r.get("last_played")
            if not lp:
                return 0
            try:
                return _dt.datetime.fromisoformat(
                    lp.replace("Z", "+00:00")
                ).timestamp() * 1000
            except Exception:
                return 0

        if policy == "lru":
            rows.sort(key=lambda r: last_played_ms(r))
        elif policy == "lfu":
            rows.sort(key=lambda r: r.get("play_count_30d") or 0)
        else:  # hybrid
            def score(r):
                lp = last_played_ms(r)
                recency = 1 - ((now_ms - lp) / thirty_days_ms) if lp else 0
                recency = max(0.0, min(1.0, recency))
                freq = min((r.get("play_count_30d") or 0) / 20.0, 1.0)
                return recency * 0.6 + freq * 0.4
            rows.sort(key=score)
        return rows

    async def get_cold_tracks(self) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM library_tracks WHERE location = 'telegram' "
            "ORDER BY file_path ASC"
        )
        return [dict(r) for r in await cur.fetchall()]

    async def set_track_location(self, file_path: str, location: str) -> None:
        await self._conn.execute(
            "UPDATE library_tracks SET location = ? WHERE file_path = ?",
            (location, file_path),
        )
        await self._conn.commit()

    async def update_track_played(self, file_path: str, played_at: str,
                                  play_count_30d: Optional[int] = None) -> None:
        if play_count_30d is None:
            await self._conn.execute(
                "UPDATE library_tracks SET last_played = ? WHERE file_path = ?",
                (played_at, file_path),
            )
        else:
            await self._conn.execute(
                "UPDATE library_tracks SET last_played = ?, play_count_30d = ? "
                "WHERE file_path = ?",
                (played_at, play_count_30d, file_path),
            )
        await self._conn.commit()

    async def set_telegram_backed(self, file_path: str, msg_id: int,
                                  file_id: str) -> None:
        await self._conn.execute(
            "UPDATE library_tracks SET telegram_backed = 1, telegram_msg_id = ?, "
            "telegram_file_id = ?, location = 'both' WHERE file_path = ?",
            (msg_id, file_id, file_path),
        )
        await self._conn.commit()

    async def get_non_backed_tracks(self) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM library_tracks WHERE telegram_backed = 0"
        )
        return [dict(r) for r in await cur.fetchall()]

    async def count_pinned(self) -> int:
        cur = await self._conn.execute(
            "SELECT COUNT(*) FROM library_tracks WHERE is_pinned = 1"
        )
        row = await cur.fetchone()
        return row[0] if row else 0

    async def count_by_location(self, location: str) -> int:
        cur = await self._conn.execute(
            "SELECT COUNT(*) FROM library_tracks WHERE location = ?", (location,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0

    async def sync_pinned_from_navidrome(self, starred_song_ids: set) -> None:
        """Pin tracks whose deezer_id is starred; this is best-effort and only
        sets pins (does not unpin radio-liked tracks)."""
        if not starred_song_ids:
            return
        # starred_song_ids are Navidrome IDs; we can only match what we know.
        # Pin library tracks whose deezer_id string is in the set as a fallback.
        await self._conn.executemany(
            "UPDATE library_tracks SET is_pinned = 1 WHERE deezer_id = ?",
            [(sid,) for sid in starred_song_ids],
        )
        await self._conn.commit()

    # ── telegram_files ──────────────────────────────────────────────────────

    async def add_telegram_file(self, file_path: str, msg_id: int, file_id: str,
                                size_mb: Optional[float]) -> None:
        await self._conn.execute(
            """INSERT INTO telegram_files (file_path, msg_id, file_id, file_size_mb, uploaded_at, status)
               VALUES (?, ?, ?, ?, ?, 'active')
               ON CONFLICT(file_path) DO UPDATE SET
                 msg_id=excluded.msg_id, file_id=excluded.file_id,
                 file_size_mb=excluded.file_size_mb, status='active'""",
            (file_path, msg_id, file_id, size_mb, _now_iso()),
        )
        await self._conn.commit()

    async def get_telegram_file(self, file_path: str) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM telegram_files WHERE file_path = ? AND status = 'active'",
            (file_path,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def delete_telegram_file(self, file_path: str) -> None:
        await self._conn.execute(
            "UPDATE telegram_files SET status = 'deleted' WHERE file_path = ?",
            (file_path,),
        )
        await self._conn.commit()

    async def telegram_stats(self) -> dict:
        cur = await self._conn.execute(
            "SELECT COUNT(*) AS c, COALESCE(SUM(file_size_mb),0) AS mb "
            "FROM telegram_files WHERE status = 'active'"
        )
        row = await cur.fetchone()
        return {
            "backed_up_files": row["c"],
            "total_backed_gb": round((row["mb"] or 0) / 1024.0, 3),
        }

    # ── radio ─────────────────────────────────────────────────────────────────

    async def create_radio_session(self, user_id: int, seed_type: str,
                                    seed_deezer_id: int, seed_title: str,
                                    seed_cover_url: Optional[str],
                                    expires_at: str, track_count: int = 0) -> str:
        sid = secrets.token_hex(16)
        await self._conn.execute(
            """INSERT INTO radio_sessions
                   (id, user_id, seed_type, seed_deezer_id, seed_title,
                    seed_cover_url, status, track_count, tracks_ready,
                    created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, 'active', ?, 0, ?, ?)""",
            (sid, user_id, seed_type, seed_deezer_id, seed_title, seed_cover_url,
             track_count, _now_iso(), expires_at),
        )
        await self._conn.commit()
        return sid

    async def update_radio_session(self, id: str, **fields) -> None:
        cols = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [id]
        await self._conn.execute(
            f"UPDATE radio_sessions SET {cols} WHERE id = ?", tuple(vals)
        )
        await self._conn.commit()

    async def get_radio_session(self, id: str) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM radio_sessions WHERE id = ?", (id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def list_radio_sessions(self, user_id: int) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM radio_sessions WHERE user_id = ? AND status = 'active' "
            "ORDER BY created_at DESC",
            (user_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def count_active_radio_sessions(self) -> int:
        cur = await self._conn.execute(
            "SELECT COUNT(*) FROM radio_sessions WHERE status = 'active'"
        )
        row = await cur.fetchone()
        return row[0] if row else 0

    async def add_radio_track(self, session_id: str, deezer_track_id: int,
                              **fields) -> int:
        fields["session_id"] = session_id
        fields["deezer_track_id"] = deezer_track_id
        cols = list(fields.keys())
        placeholders = ", ".join("?" for _ in cols)
        cur = await self._conn.execute(
            f"INSERT INTO radio_tracks ({', '.join(cols)}) VALUES ({placeholders})",
            tuple(fields[c] for c in cols),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def update_radio_track(self, id: int, **fields) -> None:
        cols = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [id]
        await self._conn.execute(
            f"UPDATE radio_tracks SET {cols} WHERE id = ?", tuple(vals)
        )
        await self._conn.commit()

    async def get_radio_track(self, session_id: str, deezer_track_id: int) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM radio_tracks WHERE session_id = ? AND deezer_track_id = ?",
            (session_id, deezer_track_id),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_radio_track_by_download(self, download_id: int) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM radio_tracks WHERE download_id = ?", (download_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def list_radio_tracks(self, session_id: str) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM radio_tracks WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def list_active_radio_tracks(self, session_id: str) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM radio_tracks WHERE session_id = ? "
            "AND status NOT IN ('liked','deleted')",
            (session_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def radio_track_active_for_path(self, rel_path: str) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT rt.* FROM radio_tracks rt "
            "JOIN radio_sessions rs ON rs.id = rt.session_id "
            "WHERE rt.rel_path = ? AND rt.status NOT IN ('deleted','liked') "
            "AND rs.status = 'active'",
            (rel_path,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def increment_radio_tracks_ready(self, session_id: str) -> None:
        await self._conn.execute(
            "UPDATE radio_sessions SET tracks_ready = tracks_ready + 1 WHERE id = ?",
            (session_id,),
        )
        await self._conn.commit()

    async def count_radio_tracks_downloading(self) -> int:
        cur = await self._conn.execute(
            "SELECT COUNT(*) FROM radio_tracks WHERE status IN ('pending','downloading')"
        )
        row = await cur.fetchone()
        return row[0] if row else 0

    async def get_expired_active_sessions(self) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM radio_sessions WHERE status = 'active' AND expires_at < ?",
            (_now_iso(),),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def dismiss_radio_session(self, id: str) -> None:
        await self._conn.execute(
            "UPDATE radio_sessions SET status = 'dismissed' WHERE id = ?", (id,)
        )
        await self._conn.commit()

    # ── lyrics ────────────────────────────────────────────────────────────────

    async def get_lyrics(self, deezer_track_id: int) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM lyrics_cache WHERE deezer_track_id = ?",
            (deezer_track_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def upsert_lyrics(self, deezer_track_id: int, synced: Optional[str],
                            plain: Optional[str], source: Optional[str]) -> None:
        await self._conn.execute(
            """INSERT INTO lyrics_cache (deezer_track_id, synced, plain, source, fetched_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(deezer_track_id) DO UPDATE SET
                 synced=excluded.synced, plain=excluded.plain,
                 source=excluded.source, fetched_at=excluded.fetched_at""",
            (deezer_track_id, synced, plain, source, _now_iso()),
        )
        await self._conn.commit()

    # ── metrics ─────────────────────────────────────────────────────────────

    async def insert_metrics(self, cpu: float, ram: float, disk: float,
                             queue_depth: int, active_users: int) -> None:
        await self._conn.execute(
            """INSERT INTO metrics_history
                   (recorded_at, cpu_percent, ram_mb, disk_gb, queue_depth, active_users)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (_now_iso(), cpu, ram, disk, queue_depth, active_users),
        )
        await self._conn.commit()

    async def get_metrics_history(self, hours: int = 24) -> list[dict]:
        cutoff = (
            _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        cur = await self._conn.execute(
            "SELECT * FROM metrics_history WHERE recorded_at >= ? "
            "ORDER BY recorded_at ASC",
            (cutoff,),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def delete_old_metrics(self, days: int = 7) -> None:
        cutoff = (
            _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        await self._conn.execute(
            "DELETE FROM metrics_history WHERE recorded_at < ?", (cutoff,)
        )
        await self._conn.commit()

    # ── settings ──────────────────────────────────────────────────────────────

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
