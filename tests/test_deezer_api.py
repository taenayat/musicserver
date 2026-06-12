"""Tests for deezer_api normalizers + preview helper."""

import deezer_api
from conftest import RAW_ALBUM, RAW_ARTIST, RAW_TRACK


def test_normalize_artist():
    obj = deezer_api.normalize_artist(RAW_ARTIST)
    assert obj == {
        "id": 27,
        "name": "Daft Punk",
        "cover_url": RAW_ARTIST["picture_xl"],
        "nb_album": 25,
        "deezer_url": "https://www.deezer.com/artist/27",
    }


def test_normalize_artist_builds_url_when_link_missing():
    obj = deezer_api.normalize_artist({"id": 99, "name": "X"})
    assert obj["deezer_url"] == "https://www.deezer.com/artist/99"
    assert obj["cover_url"] == ""        # no picture_* present


def test_normalize_album():
    obj = deezer_api.normalize_album(RAW_ALBUM)
    assert obj["id"] == 302127
    assert obj["title"] == "Discovery"
    assert obj["artist_name"] == "Daft Punk"
    assert obj["artist_id"] == 27
    assert obj["cover_url"] == RAW_ALBUM["cover_xl"]
    assert obj["nb_tracks"] == 14
    assert obj["release_year"] == 2001
    assert obj["deezer_url"] == "https://www.deezer.com/album/302127"


def test_normalize_album_fallback_artist():
    # /artist/{id}/albums omits the artist sub-object.
    raw = {k: v for k, v in RAW_ALBUM.items() if k != "artist"}
    obj = deezer_api.normalize_album(raw, fallback_artist={"id": 27, "name": "Daft Punk"})
    assert obj["artist_id"] == 27
    assert obj["artist_name"] == "Daft Punk"


def test_normalize_track():
    obj = deezer_api.normalize_track(RAW_TRACK)
    assert obj["id"] == 3135556
    assert obj["title"] == "Harder Better Faster Stronger"
    assert obj["artist_name"] == "Daft Punk"
    assert obj["artist_id"] == 27
    assert obj["album_title"] == "Discovery"
    assert obj["album_id"] == 302127
    assert obj["duration"] == 224                 # REAL duration, not 30
    assert obj["preview_url"] == RAW_TRACK["preview"]
    assert obj["track_no"] == 5                    # from track_position


def test_normalize_track_explicit_track_no_and_fallback_album():
    raw = {k: v for k, v in RAW_TRACK.items() if k not in ("album", "track_position")}
    obj = deezer_api.normalize_track(raw, fallback_album=RAW_ALBUM, track_no=3)
    assert obj["track_no"] == 3
    assert obj["album_id"] == 302127
    assert obj["cover_url"] == RAW_ALBUM["cover_xl"]


def test_year_from_release_date_bad_input():
    assert deezer_api._year_from_release_date("") == 0
    assert deezer_api._year_from_release_date("nope") == 0
    assert deezer_api._year_from_release_date("1999-01-01") == 1999


async def test_get_track_preview_url(monkeypatch):
    client = deezer_api.DeezerClient()
    try:
        async def fake_get_track(tid):
            assert tid == 42
            return {"id": 42, "preview": "https://cdns-preview-x.dzcdn.net/x.mp3"}
        monkeypatch.setattr(client, "get_track", fake_get_track)
        assert await client.get_track_preview_url(42) == "https://cdns-preview-x.dzcdn.net/x.mp3"

        async def fake_empty(tid):
            return {}
        monkeypatch.setattr(client, "get_track", fake_empty)
        assert await client.get_track_preview_url(42) == ""
    finally:
        await client.close()
