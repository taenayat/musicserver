"""
Shared pytest fixtures + fakes for the gateway backend.

Lives at the package root so `import main` resolves and so the env vars
navidrome.py reads at import time are set before any test module loads it.
"""

import os
import sys

# Make `import main` etc. work no matter where pytest is invoked from.
sys.path.insert(0, os.path.dirname(__file__))

# navidrome.py reads these at import; main.py imports navidrome. Set first.
os.environ.setdefault("NAVIDROME_USER", "admin")
os.environ.setdefault("NAVIDROME_PASS", "secret")
os.environ.setdefault("NAVIDROME_URL", "http://navidrome:4533")
os.environ.setdefault("GATEWAY_API_KEY", "test-key-123")
os.environ.setdefault("DEEZER_ARL", "deadbeefarl")

import httpx
import pytest
import pytest_asyncio

API_KEY = os.environ["GATEWAY_API_KEY"]
AUTH = {"Authorization": f"Bearer {API_KEY}"}


# ── Raw Deezer sample payloads (what the real API returns) ─────────────────────

RAW_ARTIST = {
    "id": 27,
    "name": "Daft Punk",
    "nb_album": 25,
    "picture_xl": "https://e-cdns-images.dzcdn.net/images/artist/abc/1000x1000-000000-80-0-0.jpg",
    "picture_big": "https://e-cdns-images.dzcdn.net/images/artist/abc/500x500-000000-80-0-0.jpg",
    "link": "https://www.deezer.com/artist/27",
}

RAW_ALBUM = {
    "id": 302127,
    "title": "Discovery",
    "artist": {"id": 27, "name": "Daft Punk"},
    "cover_xl": "https://e-cdns-images.dzcdn.net/images/cover/def/1000x1000-000000-80-0-0.jpg",
    "cover_big": "https://e-cdns-images.dzcdn.net/images/cover/def/500x500-000000-80-0-0.jpg",
    "nb_tracks": 14,
    "release_date": "2001-03-07",
    "link": "https://www.deezer.com/album/302127",
}

RAW_TRACK = {
    "id": 3135556,
    "title": "Harder Better Faster Stronger",
    "artist": {"id": 27, "name": "Daft Punk"},
    "album": {
        "id": 302127,
        "title": "Discovery",
        "cover_xl": "https://e-cdns-images.dzcdn.net/images/cover/def/1000x1000-000000-80-0-0.jpg",
    },
    "duration": 224,
    "preview": "https://cdns-preview-x.dzcdn.net/stream/abc.mp3",
    "track_position": 5,
}


# ── Fakes ──────────────────────────────────────────────────────────────────────

class FakeDeezer:
    """Stand-in for DeezerClient with canned, per-test-overridable responses."""

    def __init__(self):
        self.artist = dict(RAW_ARTIST)
        self.albums = [dict(RAW_ALBUM)]
        self.top_tracks = [dict(RAW_TRACK)]
        self.album = {**RAW_ALBUM, "tracks": {"data": [dict(RAW_TRACK)]}}
        self.preview_url = RAW_TRACK["preview"]
        self.search_result = {
            "artists": [{"id": 27, "name": "Daft Punk", "cover_url": "x",
                         "nb_album": 25, "deezer_url": "https://www.deezer.com/artist/27"}],
            "albums": [],
            "tracks": [],
        }

    async def search(self, query, limit=20):
        return self.search_result

    async def get_artist(self, artist_id):
        return self.artist

    async def get_artist_albums(self, artist_id, limit=100):
        return self.albums

    async def get_artist_top_tracks(self, artist_id, limit=20):
        return self.top_tracks

    async def get_album(self, album_id):
        return self.album

    async def get_track_preview_url(self, track_id):
        return self.preview_url


class FakeNavidrome:
    def __init__(self):
        self.scans = 0

    async def trigger_scan(self):
        self.scans += 1


class _FakeStreamCtx:
    def __init__(self, chunks):
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def aiter_bytes(self):
        for c in self._chunks:
            yield c


class FakeResponse:
    def __init__(self, content=b"IMGDATA", content_type="image/jpeg", status=200):
        self.content = content
        self.headers = {"content-type": content_type}
        self._status = status

    def raise_for_status(self):
        if self._status >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)


class FakeHTTP:
    """Stand-in for the module-level httpx client used by preview/cover."""

    def __init__(self):
        self.stream_chunks = [b"AUDIO", b"BYTES"]
        self.get_response = FakeResponse()
        self.streamed_url = None
        self.got_url = None

    def stream(self, method, url):
        self.streamed_url = url
        return _FakeStreamCtx(self.stream_chunks)

    async def get(self, url):
        self.got_url = url
        return self.get_response


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def database(tmp_path):
    from db import init_db
    d = await init_db(str(tmp_path / "gateway.db"))
    yield d
    await d.close()


@pytest_asyncio.fixture
async def client():
    """
    Async HTTP client bound to the app over ASGITransport — runs on the SAME
    event loop as the test, so aiosqlite connections created in-test are usable.
    Lifespan is NOT started; services are injected via dependency_overrides.
    """
    import main
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_overrides():
    import main
    main.app.dependency_overrides.clear()
    yield
    main.app.dependency_overrides.clear()
