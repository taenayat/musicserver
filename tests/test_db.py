"""Tests for the SQLite persistence layer (db.py)."""

import db as dbmod


# ── downloads ─────────────────────────────────────────────────────────────

async def test_add_and_get_queue(database):
    dl_id = await database.add_download(
        source="deezer", url="https://www.deezer.com/track/123",
        deezer_type="track", deezer_id=123, title="Song", artist="Artist",
        cover_url="http://c")
    assert isinstance(dl_id, int) and dl_id > 0

    items = await database.get_queue()
    assert len(items) == 1
    item = items[0]
    assert item["type"] == "track"          # deezer_type surfaced as "type"
    assert item["deezer_id"] == 123
    assert item["title"] == "Song"
    assert item["status"] == "pending"
    assert item["queued_at"].endswith("Z") and "T" in item["queued_at"]


async def test_update_status_and_fields(database):
    dl_id = await database.add_download(source="deezer", url="u", deezer_type="album",
                                        deezer_id=9)
    await database.update_download_status(dl_id, "downloading", started_at="2026-01-01T00:00:00Z")
    row = await database.get_download(dl_id)
    assert row["status"] == "downloading"

    await database.update_download_status(dl_id, "done", finished_at="2026-01-01T00:01:00Z",
                                          file_path="a/b.mp3")
    row = await database.get_download(dl_id)
    assert row["status"] == "done"
    assert row["file_path"] == "a/b.mp3"
    assert row["finished_at"].endswith("Z")


async def test_get_oldest_pending_is_fifo(database):
    first = await database.add_download(source="deezer", url="u1", deezer_type="track", deezer_id=1)
    second = await database.add_download(source="deezer", url="u2", deezer_type="track", deezer_id=2)
    nxt = await database.get_oldest_pending()
    assert nxt["id"] == first
    await database.update_download_status(first, "done")
    assert (await database.get_oldest_pending())["id"] == second
    await database.update_download_status(second, "done")
    assert await database.get_oldest_pending() is None


async def test_reset_interrupted_downloads(database):
    a = await database.add_download(source="deezer", url="u1", deezer_type="track", deezer_id=1)
    b = await database.add_download(source="deezer", url="u2", deezer_type="track", deezer_id=2)
    await database.update_download_status(a, "downloading")
    await database.update_download_status(b, "done")
    reset = await database.reset_interrupted_downloads()
    assert reset == 1
    assert (await database.get_download(a))["status"] == "pending"
    assert (await database.get_download(b))["status"] == "done"


async def test_count_active_and_clear(database):
    a = await database.add_download(source="deezer", url="u1", deezer_type="track", deezer_id=1)
    await database.add_download(source="deezer", url="u2", deezer_type="track", deezer_id=2)
    assert await database.count_active_downloads() == 2
    await database.update_download_status(a, "done")
    assert await database.count_active_downloads() == 1
    removed = await database.clear_finished_downloads()
    assert removed == 1


async def test_radio_downloads_excluded_from_queue(database):
    await database.add_download(source="deezer", url="u", deezer_type="track",
                                deezer_id=1, radio_session_id="sess")
    assert await database.get_queue() == []


# ── users + sessions ────────────────────────────────────────────────────────

async def test_user_crud(database):
    uid = await database.create_user("alice", "hash", "admin", nav_user="alice",
                                     nav_pass_enc="enc", nav_id="nv1")
    u = await database.get_user_by_username("alice")
    assert u["id"] == uid and u["role"] == "admin"
    assert (await database.get_user_by_id(uid))["username"] == "alice"
    assert await database.count_users() == 1
    await database.update_user_role(uid, "user")
    assert (await database.get_user_by_id(uid))["role"] == "user"
    await database.delete_user(uid)
    assert await database.get_user_by_id(uid) is None


async def test_session_lifecycle(database):
    uid = await database.create_user("bob", "h")
    token = await database.create_session(uid)
    assert len(token) == 64
    s = await database.get_session(token)
    assert s["user_id"] == uid
    await database.delete_session(token)
    assert await database.get_session(token) is None


async def test_expired_session_rejected(database):
    uid = await database.create_user("carol", "h")
    token = await database.create_session(uid, ttl_days=-1)
    assert await database.get_session(token) is None


# ── library ─────────────────────────────────────────────────────────────────

async def test_upsert_and_lookup_library(database):
    await database.upsert_library_track(
        file_path="A/B/01.mp3", title="One", artist="A", album="B",
        fingerprint="one a", duration_sec=200, file_size_mb=5.0,
        format="mp3", deezer_id=42, location="both")
    by_path = await database.get_library_track_by_path("A/B/01.mp3")
    assert by_path["title"] == "One"
    assert (await database.get_library_track_by_deezer_id(42))["album"] == "B"
    assert (await database.get_library_track_by_fingerprint("one a"))["artist"] == "A"
    await database.upsert_library_track(file_path="A/B/01.mp3", title="One!",
                                        artist="A", fingerprint="one a")
    assert (await database.get_library_track_by_path("A/B/01.mp3"))["title"] == "One!"
    stats = await database.library_stats()
    assert stats["total_tracks"] == 1


async def test_evictable_excludes_pinned_and_unbacked(database):
    await database.upsert_library_track(file_path="x/1.mp3", title="1", artist="a",
                                        fingerprint="1 a", file_size_mb=1.0,
                                        location="both", is_pinned=0)
    await database.upsert_library_track(file_path="x/2.mp3", title="2", artist="a",
                                        fingerprint="2 a", file_size_mb=1.0,
                                        location="both", is_pinned=1)
    await database.upsert_library_track(file_path="x/3.mp3", title="3", artist="a",
                                        fingerprint="3 a", file_size_mb=1.0,
                                        location="local")
    ev = await database.get_evictable_tracks("hybrid", 7)
    assert {t["file_path"] for t in ev} == {"x/1.mp3"}


# ── telegram + lyrics + metrics ──────────────────────────────────────────────

async def test_telegram_files(database):
    await database.add_telegram_file("a/b.mp3", 10, "fid", 4.2)
    tf = await database.get_telegram_file("a/b.mp3")
    assert tf["msg_id"] == 10 and tf["file_id"] == "fid"
    await database.delete_telegram_file("a/b.mp3")
    assert await database.get_telegram_file("a/b.mp3") is None


async def test_lyrics_cache(database):
    assert await database.get_lyrics(5) is None
    await database.upsert_lyrics(5, "[00:01.00]hi", "hi", "lrclib")
    row = await database.get_lyrics(5)
    assert row["source"] == "lrclib" and row["plain"] == "hi"


async def test_metrics(database):
    await database.insert_metrics(10.0, 50.0, 1.0, 2, 1)
    pts = await database.get_metrics_history(24)
    assert len(pts) == 1 and pts[0]["queue_depth"] == 2


async def test_settings_roundtrip(database):
    assert await database.get_setting("missing") is None
    await database.set_setting("k", "v1")
    assert await database.get_setting("k") == "v1"
    await database.set_setting("k", "v2")
    assert await database.get_setting("k") == "v2"


def test_iso_helper():
    assert dbmod._iso(None) is None
    assert dbmod._iso("2026-05-30 12:00:00") == "2026-05-30T12:00:00Z"
    assert dbmod._iso("2026-05-30T12:00:00Z") == "2026-05-30T12:00:00Z"
