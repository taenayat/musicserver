"""Tests for the SQLite queue layer (db.py)."""

import db as dbmod


async def test_add_and_get_queue(database):
    dl_id = await database.add_download(
        "track", 123, "https://www.deezer.com/track/123",
        title="Song", artist="Artist", cover_url="http://c",
    )
    assert isinstance(dl_id, int) and dl_id > 0

    items = await database.get_queue()
    assert len(items) == 1
    item = items[0]
    # API shape: deezer_type column surfaces as "type".
    assert item["type"] == "track"
    assert item["deezer_id"] == 123
    assert item["title"] == "Song"
    assert item["status"] == "pending"
    assert item["finished_at"] is None
    # queued_at normalised to ISO-8601 with a Z.
    assert item["queued_at"].endswith("Z") and "T" in item["queued_at"]


async def test_status_transitions_set_finished_at(database):
    dl_id = await database.add_download("album", 9, "u")
    await database.set_download_status(dl_id, "downloading")
    row = await database.get_download(dl_id)
    assert row["status"] == "downloading"
    assert row["finished_at"] is None

    await database.set_download_status(dl_id, "done")
    row = await database.get_download(dl_id)
    assert row["status"] == "done"
    assert row["finished_at"] is not None and row["finished_at"].endswith("Z")

    await database.set_download_status(dl_id, "error", error_msg="oops")
    row = await database.get_download(dl_id)
    assert row["status"] == "error"
    assert row["error_msg"] == "oops"
    assert row["finished_at"] is not None


async def test_get_queue_orders_newest_first_and_limits(database):
    ids = []
    for i in range(5):
        ids.append(await database.add_download("track", i, f"u{i}"))
    items = await database.get_queue(limit=3)
    assert len(items) == 3
    # Newest (largest id / latest queued_at) first.
    assert items[0]["deezer_id"] == 4
    assert [it["id"] for it in items] == sorted([it["id"] for it in items], reverse=True)


async def test_delete_download(database):
    dl_id = await database.add_download("track", 1, "u")
    await database.delete_download(dl_id)
    assert await database.get_download(dl_id) is None
    assert await database.get_queue() == []


async def test_reset_stuck_downloads(database):
    a = await database.add_download("track", 1, "u1")
    b = await database.add_download("track", 2, "u2")
    await database.set_download_status(a, "downloading")
    await database.set_download_status(b, "done")

    reset = await database.reset_stuck_downloads()
    assert reset == 1
    assert (await database.get_download(a))["status"] == "pending"
    assert (await database.get_download(a))["finished_at"] is None
    assert (await database.get_download(b))["status"] == "done"   # untouched


async def test_next_pending_is_fifo(database):
    first = await database.add_download("track", 1, "u1")
    second = await database.add_download("track", 2, "u2")
    nxt = await database.next_pending()
    assert nxt["id"] == first

    await database.set_download_status(first, "done")
    nxt = await database.next_pending()
    assert nxt["id"] == second

    await database.set_download_status(second, "done")
    assert await database.next_pending() is None


async def test_count_pending(database):
    a = await database.add_download("track", 1, "u1")
    await database.add_download("track", 2, "u2")
    assert await database.count_pending() == 2
    await database.set_download_status(a, "downloading")
    assert await database.count_pending() == 2   # downloading still counts
    await database.set_download_status(a, "done")
    assert await database.count_pending() == 1


async def test_settings_roundtrip(database):
    assert await database.get_setting("missing") is None
    await database.set_setting("k", "v1")
    assert await database.get_setting("k") == "v1"
    await database.set_setting("k", "v2")     # upsert
    assert await database.get_setting("k") == "v2"


def test_iso_helper():
    assert dbmod._iso(None) is None
    assert dbmod._iso("2026-05-30 12:00:00") == "2026-05-30T12:00:00Z"
    assert dbmod._iso("2026-05-30T12:00:00Z") == "2026-05-30T12:00:00Z"
