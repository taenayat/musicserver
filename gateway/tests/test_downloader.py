"""Tests for the SQLite-backed Downloader worker (downloader.py)."""

import asyncio

import pytest

from conftest import FakeNavidrome
from downloader import Downloader


@pytest.fixture
async def dl(database, tmp_path):
    return Downloader(
        arl="x", music_dir=str(tmp_path / "music"), navidrome=FakeNavidrome(),
        db=database, config_dir=str(tmp_path / "cfg"),
    )


def test_configure_writes_arl_and_config(dl, tmp_path):
    cfg = tmp_path / "cfg"
    assert (cfg / ".arl").read_text() == "x"
    import json
    data = json.loads((cfg / "config.json").read_text())
    assert data["fallbackBitrate"] is True
    assert data["overwriteFile"] == "n"


async def test_enqueue_persists_and_builds_url(dl, database):
    dl_id = await dl.enqueue("track", 123, title="T", artist="A")
    row = await database.get_download(dl_id)
    assert row["status"] == "pending"
    assert row["type"] == "track"

    aid = await dl.enqueue("album", 9)
    # The url stored on each row is what drives the deemix call.
    cur = await database._conn.execute("SELECT url FROM downloads WHERE id=?", (dl_id,))
    assert (await cur.fetchone())["url"] == "https://www.deezer.com/track/123"
    cur = await database._conn.execute("SELECT url FROM downloads WHERE id=?", (aid,))
    assert (await cur.fetchone())["url"] == "https://www.deezer.com/album/9"


async def test_enqueue_rejects_bad_type(dl):
    with pytest.raises(ValueError):
        await dl.enqueue("artist", 1)


async def test_process_success_marks_done_and_scans(dl, database, monkeypatch):
    async def fake_download(url):
        return True, "all good"
    monkeypatch.setattr(dl, "_download", fake_download)

    dl_id = await dl.enqueue("track", 1)
    row = await database.next_pending()
    await dl._process(row)

    done = await database.get_download(dl_id)
    assert done["status"] == "done"
    assert done["finished_at"] is not None
    assert dl.navidrome.scans == 1


async def test_process_failure_marks_error_with_tail(dl, database, monkeypatch):
    long_output = "E" * 1000
    async def fake_download(url):
        return False, long_output
    monkeypatch.setattr(dl, "_download", fake_download)

    dl_id = await dl.enqueue("track", 1)
    row = await database.next_pending()
    await dl._process(row)

    err = await database.get_download(dl_id)
    assert err["status"] == "error"
    assert len(err["error_msg"]) == 500          # last 500 chars only
    assert dl.navidrome.scans == 0               # no scan on failure


async def test_failure_marker_detection(dl, monkeypatch):
    # returncode 0 but output contains a failure marker → treated as failure.
    class FakeProc:
        returncode = 0
        async def communicate(self):
            return (b"Track not found on Deezer", b"")

    async def fake_exec(*a, **k):
        return FakeProc()
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    ok, out = await dl._download("https://www.deezer.com/track/1")
    assert ok is False
    assert "marker" in out


async def test_download_missing_cli(dl, monkeypatch):
    async def boom(*a, **k):
        raise FileNotFoundError()
    monkeypatch.setattr("asyncio.create_subprocess_exec", boom)
    ok, out = await dl._download("https://www.deezer.com/track/1")
    assert ok is False
    assert "deemix CLI not found" in out


async def test_worker_resumes_and_processes(database, tmp_path, monkeypatch):
    """Full loop: a pre-existing pending row gets picked up after start()."""
    dl = Downloader(
        arl="x", music_dir=str(tmp_path / "m"), navidrome=FakeNavidrome(),
        db=database, config_dir=str(tmp_path / "c"),
    )

    processed = []
    async def fake_download(url):
        processed.append(url)
        return True, "ok"
    monkeypatch.setattr(dl, "_download", fake_download)

    # Simulate an interrupted download left over from a previous run.
    stuck = await database.add_download("track", 7, "https://www.deezer.com/track/7")
    await database.set_download_status(stuck, "downloading")

    await dl.start()                       # resets stuck → pending, starts worker
    try:
        for _ in range(100):               # up to ~5s
            row = await database.get_download(stuck)
            if row["status"] == "done":
                break
            await asyncio.sleep(0.05)
    finally:
        await dl.stop()

    assert row["status"] == "done"
    assert processed == ["https://www.deezer.com/track/7"]
    assert dl.navidrome.scans == 1
