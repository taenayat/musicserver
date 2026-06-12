"""Tests for the SQLite-backed Downloader worker (downloader.py)."""

import asyncio
import os
from pathlib import Path

import pytest

from conftest import FakeNavidrome
from downloader import Downloader


@pytest.fixture
async def dl(database, tmp_path):
    return Downloader(
        arl="x", music_dir=str(tmp_path / "music"), navidrome=FakeNavidrome(),
        db=database, config_dir=str(tmp_path / "cfg"))


def test_configure_writes_arl_and_config(dl, tmp_path):
    cfg = tmp_path / "cfg"
    assert (cfg / ".arl").read_text() == "x"
    import json
    data = json.loads((cfg / "config.json").read_text())
    assert data["fallbackBitrate"] is True
    assert data["overwriteFile"] == "n"


async def test_enqueue_persists_and_builds_url(dl, database):
    dl_id = await dl.enqueue("deezer", deezer_type="track", deezer_id=123,
                             title="T", artist="A")
    row = await database.get_download(dl_id)
    assert row["status"] == "pending"
    assert row["type"] == "track"
    assert row["url"] == "https://www.deezer.com/track/123"

    aid = await dl.enqueue("deezer", deezer_type="album", deezer_id=9)
    assert (await database.get_download(aid))["url"] == "https://www.deezer.com/album/9"


async def test_enqueue_rejects_bad_type(dl):
    with pytest.raises(ValueError):
        await dl.enqueue("deezer", deezer_type="artist", deezer_id=1)


async def test_process_success_indexes_and_scans(dl, database, monkeypatch):
    async def fake_deemix(url, dest):
        os.makedirs(dest, exist_ok=True)
        with open(os.path.join(dest, "01_song.mp3"), "wb") as fh:
            fh.write(b"\x00" * 2048)
        return True, "ok"
    monkeypatch.setattr(dl, "_run_deemix", fake_deemix)

    dl_id = await dl.enqueue("deezer", deezer_type="track", deezer_id=1, artist="A")
    job = await database.get_oldest_pending()
    await dl._process(job)

    done = await database.get_download(dl_id)
    assert done["status"] == "done"
    assert done["file_path"] == "01_song.mp3"
    assert dl.navidrome.scans == 1
    assert await database.get_library_track_by_path("01_song.mp3") is not None


async def test_process_failure_marks_error_with_tail(dl, database, monkeypatch):
    async def fake_deemix(url, dest):
        return False, "E" * 1000
    monkeypatch.setattr(dl, "_run_deemix", fake_deemix)

    dl_id = await dl.enqueue("deezer", deezer_type="track", deezer_id=1)
    job = await database.get_oldest_pending()
    await dl._process(job)

    err = await database.get_download(dl_id)
    assert err["status"] == "error"
    assert len(err["error_msg"]) == 500
    assert dl.navidrome.scans == 0


async def test_process_no_new_files_is_error(dl, database, monkeypatch):
    async def fake_deemix(url, dest):
        os.makedirs(dest, exist_ok=True)
        return True, "ok"
    monkeypatch.setattr(dl, "_run_deemix", fake_deemix)
    dl_id = await dl.enqueue("deezer", deezer_type="track", deezer_id=1)
    job = await database.get_oldest_pending()
    await dl._process(job)
    assert (await database.get_download(dl_id))["status"] == "error"


async def test_failure_marker_detection(dl, monkeypatch):
    class FakeProc:
        returncode = 0
        async def communicate(self):
            return (b"Track not found on Deezer", b"")

    async def fake_exec(*a, **k):
        return FakeProc()
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    ok, out = await dl._run_deemix("https://www.deezer.com/track/1", Path("/tmp"))
    assert ok is False and "marker" in out


async def test_run_deemix_missing_cli(dl, monkeypatch):
    async def boom(*a, **k):
        raise FileNotFoundError()
    monkeypatch.setattr("asyncio.create_subprocess_exec", boom)
    ok, out = await dl._run_deemix("https://www.deezer.com/track/1", Path("/tmp"))
    assert ok is False and "deemix CLI not found" in out


async def test_worker_resumes_and_processes(database, tmp_path, monkeypatch):
    dl = Downloader(arl="x", music_dir=str(tmp_path / "m"),
                    navidrome=FakeNavidrome(), db=database,
                    config_dir=str(tmp_path / "c"))

    async def fake_deemix(url, dest):
        os.makedirs(dest, exist_ok=True)
        with open(os.path.join(dest, "t.mp3"), "wb") as fh:
            fh.write(b"\x00" * 1024)
        return True, "ok"
    monkeypatch.setattr(dl, "_run_deemix", fake_deemix)

    async def no_arl():
        dl.arl_ok = True
    monkeypatch.setattr(dl, "_validate_arl", no_arl)

    stuck = await database.add_download(source="deezer",
                                        url="https://www.deezer.com/track/7",
                                        deezer_type="track", deezer_id=7)
    await database.update_download_status(stuck, "downloading")

    await dl.start()
    try:
        for _ in range(100):
            row = await database.get_download(stuck)
            if row["status"] == "done":
                break
            await asyncio.sleep(0.05)
    finally:
        await dl.stop()

    assert row["status"] == "done"
    assert dl.navidrome.scans == 1
