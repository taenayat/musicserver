"""Route-level tests over ASGITransport with injected fakes + session auth."""

import pytest

import main
from conftest import FakeDeezer, FakeHTTP, FakeNavidrome
from downloader import Downloader


def _use_deezer(fake):
    main.app.dependency_overrides[main.get_deezer] = lambda: fake


def _use_db(database):
    main.app.dependency_overrides[main.get_db] = lambda: database


# ── health / auth gating ─────────────────────────────────────────────────────

async def test_health_no_auth_required(client):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "first_run" in body and "radio_enabled" in body


async def test_api_requires_auth(client, database):
    _use_deezer(FakeDeezer())
    _use_db(database)
    # No session override → 401.
    assert (await client.get("/api/search?q=x")).status_code == 401


async def test_api_allows_authed_user(client, database, as_user):
    _use_deezer(FakeDeezer())
    _use_db(database)
    assert (await client.get("/api/search?q=daft")).status_code == 200


# ── search ─────────────────────────────────────────────────────────────────

async def test_search_empty_query_returns_empty(client, database, as_user):
    _use_deezer(FakeDeezer())
    _use_db(database)
    r = await client.get("/api/search?q=%20%20")
    assert r.status_code == 200
    assert r.json() == {"artists": [], "albums": [], "tracks": []}


async def test_search_normalized_and_enriched(client, database, as_user):
    fake = FakeDeezer()
    fake.search_result = {
        "artists": [{"id": 27, "name": "Daft Punk"}],
        "albums": [],
        "tracks": [{"id": 5, "title": "Da Funk", "artist_name": "Daft Punk",
                    "duration": 200}],
    }
    _use_deezer(fake)
    _use_db(database)
    r = await client.get("/api/search?q=daft")
    assert r.status_code == 200
    body = r.json()
    assert body["artists"][0]["name"] == "Daft Punk"
    # enrichment adds in_library flags
    assert body["tracks"][0]["in_library"] is False


async def test_youtube_search_disabled(client, database, as_user, monkeypatch):
    monkeypatch.setenv("YTDLP_ENABLED", "false")
    _use_db(database)
    r = await client.get("/api/search/youtube?q=x")
    assert r.status_code == 503


# ── browse ─────────────────────────────────────────────────────────────────

async def test_artist_page(client, database, as_user):
    fake = FakeDeezer()
    fake.albums = [
        {**dict(fake.albums[0]), "id": 1, "release_date": "1997-01-01", "title": "Homework"},
        {**dict(fake.albums[0]), "id": 2, "release_date": "2001-01-01", "title": "Discovery"},
    ]
    _use_deezer(fake)
    _use_db(database)
    r = await client.get("/api/artist/27")
    assert r.status_code == 200
    body = r.json()
    assert body["artist"]["name"] == "Daft Punk"
    assert [a["release_year"] for a in body["albums"]] == [2001, 1997]
    assert body["top_tracks"][0]["album_id"] == 302127


async def test_artist_not_found(client, database, as_user):
    fake = FakeDeezer()
    fake.artist = {}
    _use_deezer(fake)
    _use_db(database)
    assert (await client.get("/api/artist/999")).status_code == 404


async def test_album_page_enumerates_tracks(client, database, as_user):
    fake = FakeDeezer()
    fake.album = {**dict(fake.album),
                  "tracks": {"data": [{"id": 10, "title": "One"},
                                      {"id": 11, "title": "Two"}]}}
    _use_deezer(fake)
    _use_db(database)
    r = await client.get("/api/album/302127")
    assert r.status_code == 200
    body = r.json()
    assert [t["track_no"] for t in body["tracks"]] == [1, 2]
    assert body["tracks"][0]["album_id"] == 302127


# ── preview ─────────────────────────────────────────────────────────────────

async def test_preview_streams_audio(client, as_user, monkeypatch):
    fake = FakeDeezer()
    _use_deezer(fake)
    fhttp = FakeHTTP()
    monkeypatch.setattr(main, "http", fhttp)
    r = await client.get("/api/preview/3135556")
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.headers["cache-control"] == "no-store"
    assert r.content == b"AUDIOBYTES"
    assert fhttp.streamed_url == fake.preview_url


async def test_preview_404_when_none(client, as_user):
    fake = FakeDeezer()
    fake.preview_url = ""
    _use_deezer(fake)
    r = await client.get("/api/preview/1")
    assert r.status_code == 404


# ── cover proxy ──────────────────────────────────────────────────────────────

async def test_cover_proxies_deezer_url(client, as_user, monkeypatch):
    fhttp = FakeHTTP()
    monkeypatch.setattr(main, "http", fhttp)
    url = "https://e-cdns-images.dzcdn.net/images/cover/x/500x500-000000-80-0-0.jpg"
    r = await client.get(f"/api/cover?url={url}&size=lg")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=86400"
    assert "1000x1000" in fhttp.got_url


async def test_cover_rejects_non_deezer(client, as_user):
    r = await client.get("/api/cover?url=https://evil.example.com/x.jpg")
    assert r.status_code == 400


def test_cover_helpers():
    assert main._cover_allowed("https://e-cdns-images.dzcdn.net/x.jpg")
    assert main._cover_allowed("https://www.deezer.com/x.jpg")
    assert not main._cover_allowed("https://evil.com/x.jpg")
    assert not main._cover_allowed("file:///etc/passwd")
    assert main._resize_cover("a/500x500-0.jpg", "sm") == "a/250x250-0.jpg"
    assert main._resize_cover("a/500x500-0.jpg", "bogus") == "a/500x500-0.jpg"


# ── downloads + queue ────────────────────────────────────────────────────────

@pytest.fixture
async def wired(database, tmp_path):
    dl = Downloader(arl="x", music_dir=str(tmp_path / "music"),
                    navidrome=FakeNavidrome(), db=database,
                    config_dir=str(tmp_path / "cfg"))
    main.app.dependency_overrides[main.get_db] = lambda: database
    main.app.dependency_overrides[main.get_downloader] = lambda: dl
    return database, dl


async def test_download_then_queue(client, wired, as_user):
    database, _ = wired
    r = await client.post("/api/download", json={
        "source": "deezer", "type": "track", "deezer_id": 555,
        "title": "T", "artist": "A", "cover_url": "c"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending" and isinstance(body["id"], int)

    items = (await client.get("/api/queue")).json()["items"]
    assert len(items) == 1
    assert items[0]["type"] == "track" and items[0]["deezer_id"] == 555


async def test_download_already_in_library(client, wired, as_user):
    database, _ = wired
    await database.upsert_library_track(
        file_path="A/T.mp3", title="T", artist="A", fingerprint="t a",
        deezer_id=777, format="mp3", bitrate_kbps=320, location="both")
    r = await client.post("/api/download", json={
        "source": "deezer", "type": "track", "deezer_id": 777,
        "title": "T", "artist": "A"})
    assert r.status_code == 200
    assert r.json()["status"] == "already_in_library"


async def test_download_force_bypasses_library(client, wired, as_user):
    database, _ = wired
    await database.upsert_library_track(
        file_path="A/T.mp3", title="T", artist="A", fingerprint="t a",
        deezer_id=777, format="mp3", location="both")
    r = await client.post("/api/download", json={
        "source": "deezer", "type": "track", "deezer_id": 777, "force": True})
    assert r.json()["status"] == "pending"


async def test_download_rejects_bad_type(client, wired, as_user):
    r = await client.post("/api/download", json={"source": "deezer",
                                                 "type": "playlist", "deezer_id": 1})
    assert r.status_code == 400


async def test_delete_queue_item(client, wired, as_user):
    database, _ = wired
    dl_id = await database.add_download(source="deezer", url="u",
                                        deezer_type="track", deezer_id=1)
    r = await client.delete(f"/api/queue/{dl_id}")
    assert r.status_code == 204
    assert await database.get_download(dl_id) is None


async def test_cannot_delete_in_progress(client, wired, as_user):
    database, _ = wired
    dl_id = await database.add_download(source="deezer", url="u",
                                        deezer_type="album", deezer_id=1)
    await database.update_download_status(dl_id, "downloading")
    r = await client.delete(f"/api/queue/{dl_id}")
    assert r.status_code == 409


# ── admin gating ─────────────────────────────────────────────────────────────

async def test_admin_route_forbidden_for_user(client, database, as_user):
    _use_db(database)
    r = await client.get("/api/admin/users")
    assert r.status_code == 403


async def test_admin_users_list(client, database, as_admin):
    _use_db(database)
    await database.create_user("alice", "h", "user")
    r = await client.get("/api/admin/users")
    assert r.status_code == 200
    assert any(u["username"] == "alice" for u in r.json())
