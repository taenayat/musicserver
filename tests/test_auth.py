"""Tests for session-based auth (auth.py)."""

import pytest
from fastapi import HTTPException

import auth


def test_password_hash_roundtrip():
    h = auth.hash_password("hunter2")
    assert auth.check_password("hunter2", h)
    assert not auth.check_password("wrong", h)


def test_fernet_roundtrip():
    c = auth.encrypt_secret("navpass")
    assert auth.decrypt_secret(c) == "navpass"


def test_public_user_strips_secrets():
    pub = auth.public_user({"id": 1, "username": "u", "role": "admin",
                            "password_hash": "SECRET", "navidrome_pass": "ENC"})
    assert "password_hash" not in pub
    assert "navidrome_pass" not in pub
    assert pub["role"] == "admin"


async def test_get_current_user_rejects_missing_header():
    with pytest.raises(HTTPException) as ei:
        await auth.get_current_user(None)
    assert ei.value.status_code == 401


async def test_get_current_user_rejects_bad_scheme():
    with pytest.raises(HTTPException) as ei:
        await auth.get_current_user("Basic abc")
    assert ei.value.status_code == 401


async def test_get_current_user_validates_session(database):
    auth.set_db_getter(lambda: database)
    uid = await database.create_user("dave", auth.hash_password("pw"))
    token = await database.create_session(uid)
    user = await auth.get_current_user(f"Bearer {token}")
    assert user["id"] == uid

    with pytest.raises(HTTPException) as ei:
        await auth.get_current_user("Bearer not-a-real-token")
    assert ei.value.status_code == 401


async def test_require_admin(database):
    auth.set_db_getter(lambda: database)
    user = {"id": 1, "role": "user"}
    with pytest.raises(HTTPException) as ei:
        await auth.require_admin(user)
    assert ei.value.status_code == 403
    admin = {"id": 2, "role": "admin"}
    assert await auth.require_admin(admin) is admin


def test_user_subsonic_auth():
    enc = auth.encrypt_secret("navpw")
    user = {"username": "u", "navidrome_user": "u", "navidrome_pass": enc}
    sub = auth.user_subsonic_auth(user)
    assert sub["u"] == "u" and "t" in sub and "s" in sub
    assert auth.user_subsonic_auth({"username": "x"}) is None
