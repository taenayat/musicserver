"""Route-level tests over ASGITransport with injected fakes."""

import pytest

import main
from conftest import AUTH, FakeDeezer, FakeHTTP, FakeNavidrome
from downloader import Downloader


def _use_deezer(fake):
    main.app.dependency_overrides[main.get_deezer] = lambda: fake


# ── Health / auth ──────────────────────────────────────────────────────────────

async def test_health_no_auth_required(client):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "arl_ok" in body


async def test_health_validates_supplied_key(client):
    assert (await client.get("/health", headers=AUTH)).status_code == 200
    bad = await client.get("/health", headers={"Authorization": "Bearer wrong"})
    assert bad.status_code == 401


async def test_api_requires_auth(client):
    _use_deezer(FakeDeezer())
    assert (await client.get("/api/search?q=x")).status_code == 401
    assert (await client.get("/api/search?q=x", headers=AUTH)).status_code == 200


# ── Search ─────────────────────────────────────────────────────────────────────

async def test_search_empty_query_returns_empty(client):
    _use_deezer(FakeDeezer())
    r = await client.get("/api/search?q=%20%20", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"artists": [], "albums": [], "tracks": []}


async def test_search_passes_through_normalized(client):
    fake = FakeDeezer()
    _use_deezer(fake)
    r = await client.get("/api/search?q=daft", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["artists"][0]["name"] == "Daft Punk"


# ── Browse ─────────────────────────────────────────────────────────────────────

async def test_artist_page(client):
    fake = FakeDeezer()
    # Two albums, different years → assert sort desc.
    fake.albums = [
        {**dict(fake.albums[0]), "id": 1, "release_date": "1997-01-01", "title": "Homework"},
        {**dict(fake.albums[0]), "id": 2, "release_date": "2001-01-01", "title": "Discovery"},
    ]
    _use_deezer(fake)
    r = await client.get("/api/artist/27", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["artist"]["name"] == "Daft Punk"
    assert [a["release_year"] for a in body["albums"]] == [2001, 1997]
    assert len(body["top_tracks"]) == 1
    assert body["top_tracks"][0]["album_id"] == 302127


async def test_artist_not_found(client):
    fake = FakeDeezer()
    fake.artist = {}
    _use_deezer(fake)
    r = await client.get("/api/artist/999", headers=AUTH)
    assert r.status_code == 404


async def test_album_page_enumerates_tracks(client):
    fake = FakeDeezer()
    fake.album = {
        **dict(fake.album),
        "tracks": {"data": [
            {"id": 10, "title": "One"},
            {"id": 11, "title": "Two"},
        ]},
    }
    _use_deezer(fake)
    r = await client.get("/api/album/302127", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["album"]["title"] == "Discovery"
    assert [t["track_no"] for t in body["tracks"]] == [1, 2]
    # fallback_album fills the album fields the embedded tracks lack.
    assert body["tracks"][0]["album_id"] == 302127


async def test_album_not_found(client):
    fake = FakeDeezer()
    fake.album = {}
    _use_deezer(fake)
    assert (await client.get("/api/album/1", headers=AUTH)).status_code == 404


# ── Preview ────────────────────────────────────────────────────────────────────

async def test_preview_streams_audio(client, monkeypatch):
    fake = FakeDeezer()
    _use_deezer(fake)
    fhttp = FakeHTTP()
    monkeypatch.setattr(main, "http", fhttp)
    r = await client.get("/api/preview/3135556", headers=AUTH)
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.headers["cache-control"] == "no-store"
    assert r.content == b"AUDIOBYTES"
    assert fhttp.streamed_url == fake.preview_url


async def test_preview_404_when_no_preview(client):
    fake = FakeDeezer()
    fake.preview_url = ""
    _use_deezer(fake)
    r = await client.get("/api/preview/1", headers=AUTH)
    assert r.status_code == 404
    assert "error" in r.json()


# ── Cover proxy ────────────────────────────────────────────────────────────────

async def test_cover_proxies_deezer_url(client, monkeypatch):
    fhttp = FakeHTTP()
    monkeypatch.setattr(main, "http", fhttp)
    url = "https://e-cdns-images.dzcdn.net/images/cover/x/500x500-000000-80-0-0.jpg"
    r = await client.get(f"/api/cover?url={url}&size=lg", headers=AUTH)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=86400"
    # size=lg rewrites the WxH segment.
    assert "1000x1000" in fhttp.got_url


async def test_cover_rejects_non_deezer_host(client):
    r = await client.get("/api/cover?url=https://evil.example.com/x.jpg", headers=AUTH)
    assert r.status_code == 400


def test_cover_helpers():
    assert main._cover_allowed("https://e-cdns-images.dzcdn.net/x.jpg")
    assert main._cover_allowed("https://www.deezer.com/x.jpg")
    assert not main._cover_allowed("https://evil.com/x.jpg")
    assert not main._cover_allowed("file:///etc/passwd")
    assert main._resize_cover("a/500x500-0.jpg", "sm") == "a/250x250-0.jpg"
    assert main._resize_cover("a/500x500-0.jpg", "bogus") == "a/500x500-0.jpg"


# ── Downloads + queue (real db + real downloader, no worker) ───────────────────

@pytest.fixture
async def wired(database, tmp_path):
    """Wire a real Downloader (no .start(), so no worker/ARL) onto the app."""
    dl = Downloader(
        arl="x", music_dir=str(tmp_path / "music"), navidrome=FakeNavidrome(),
        db=database, config_dir=str(tmp_path / "cfg"),
    )
    main.app.dependency_overrides[main.get_db] = lambda: database
    main.app.dependency_overrides[main.get_downloader] = lambda: dl
    return database, dl


async def test_download_then_queue(client, wired):
    database, _ = wired
    r = await client.post("/api/download", headers=AUTH, json={
        "type": "track", "deezer_id": 555, "title": "T", "artist": "A", "cover_url": "c",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending" and isinstance(body["id"], int)

    q = await client.get("/api/queue", headers=AUTH)
    items = q.json()["items"]
    assert len(items) == 1
    assert items[0]["type"] == "track"
    assert items[0]["deezer_id"] == 555
    assert items[0]["title"] == "T"


async def test_download_rejects_bad_type(client, wired):
    r = await client.post("/api/download", headers=AUTH,
                          json={"type": "playlist", "deezer_id": 1})
    assert r.status_code == 400


async def test_delete_queue_item(client, wired):
    database, _ = wired
    dl_id = await database.add_download("track", 1, "u")
    r = await client.delete(f"/api/queue/{dl_id}", headers=AUTH)
    assert r.status_code == 204
    assert await database.get_download(dl_id) is None


async def test_delete_missing_returns_404(client, wired):
    assert (await client.delete("/api/queue/9999", headers=AUTH)).status_code == 404


async def test_cannot_delete_in_progress(client, wired):
    database, _ = wired
    dl_id = await database.add_download("album", 1, "u")
    await database.set_download_status(dl_id, "downloading")
    r = await client.delete(f"/api/queue/{dl_id}", headers=AUTH)
    assert r.status_code == 409
    assert await database.get_download(dl_id) is not None   # still there
