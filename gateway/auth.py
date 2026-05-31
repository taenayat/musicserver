"""
auth.py — single-key bearer auth for the MVP.

All /api/* routes depend on `api_key_dep`. The one shared secret lives in the
env var GATEWAY_API_KEY; clients send it as `Authorization: Bearer <key>`.

This is deliberately minimal — no per-user accounts (that's a full-vision
feature). The frontend stores the key in localStorage after a one-time prompt.
"""

import logging
import os
import secrets

from fastapi import Depends, Header, HTTPException
from typing import Optional

log = logging.getLogger("auth")


def _expected_key() -> str:
    # Read per-call so deployment/tests can set it without import ordering games.
    return os.environ.get("GATEWAY_API_KEY", "")


def verify_key(authorization: Optional[str] = Header(default=None)) -> None:
    """
    Raise 401 unless the request carries the correct bearer token.

    Fails closed: if no GATEWAY_API_KEY is configured, every request is rejected
    rather than silently allowing open access.
    """
    expected = _expected_key()
    if not expected:
        log.error("GATEWAY_API_KEY is not set — rejecting all API requests")
        raise HTTPException(status_code=401, detail="Server auth not configured")

    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    # Constant-time compare so a wrong key can't be probed byte-by-byte via timing.
    if not secrets.compare_digest(token.strip(), expected):
        raise HTTPException(status_code=401, detail="Invalid API key")


# FastAPI dependency the routes attach to.
api_key_dep = Depends(verify_key)
