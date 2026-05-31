"""Tests for the single-key bearer auth (auth.py)."""

import os

import pytest
from fastapi import HTTPException

from auth import verify_key


def test_verify_key_accepts_correct():
    # Should not raise.
    verify_key(f"Bearer {os.environ['GATEWAY_API_KEY']}")


def test_verify_key_rejects_missing_header():
    with pytest.raises(HTTPException) as ei:
        verify_key(None)
    assert ei.value.status_code == 401


def test_verify_key_rejects_wrong_scheme():
    with pytest.raises(HTTPException) as ei:
        verify_key("Basic abc")
    assert ei.value.status_code == 401


def test_verify_key_rejects_wrong_token():
    with pytest.raises(HTTPException) as ei:
        verify_key("Bearer not-the-key")
    assert ei.value.status_code == 401


def test_verify_key_fails_closed_when_unset(monkeypatch):
    monkeypatch.delenv("GATEWAY_API_KEY", raising=False)
    with pytest.raises(HTTPException) as ei:
        verify_key("Bearer anything")
    assert ei.value.status_code == 401
