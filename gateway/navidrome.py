"""
navidrome.py — Navidrome Subsonic client.

Each gateway request passes its own user_auth dict (the validated
Subsonic auth params forwarded from the original Symfonium request).
This means play counts, starred tracks, and scrobbles are tracked
per-user inside Navidrome — not all piled onto a single admin account.

The admin credentials in env are kept only for administrative actions
(e.g. triggering a library scan) that require an admin-level account.
"""

import hashlib
import logging
import os
import secrets
from typing import Optional

import httpx

log = logging.getLogger("navidrome")

_ADMIN_USER = os.environ["NAVIDROME_USER"]
_ADMIN_PASS = os.environ["NAVIDROME_PASS"]
_BASE_URL   = os.environ["NAVIDROME_URL"].rstrip("/")


def _admin_auth() -> dict:
    salt  = secrets.token_hex(8)
    token = hashlib.md5((_ADMIN_PASS + salt).encode()).hexdigest()
    return {
        "u": _ADMIN_USER,
        "t": token,
        "s": salt,
        "v": "1.16.1",
        "c": "musicgateway",
        "f": "json",
    }


def _wrap(auth: dict) -> dict:
    """Add the standard Subsonic boilerplate if not already present."""
    base = {"v": "1.16.1", "c": "musicgateway", "f": "json"}
    return {**base, **auth}


class NavidromeClient:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self.client.aclose()

    # ── JSON calls ────────────────────────────────────────────────────────────

    async def call(
        self,
        endpoint: str,
        user_auth: Optional[dict] = None,
        **params,
    ) -> dict:
        """
        Make a JSON Subsonic call.
        user_auth: the requesting user's auth params (u, t, s or p).
                   Falls back to admin auth if not provided.
        """
        endpoint = endpoint.lstrip("/")
        if not endpoint.endswith(".view"):
            endpoint = endpoint + ".view"

        auth = _wrap(user_auth) if user_auth else _admin_auth()
        url  = f"{_BASE_URL}/rest/{endpoint}"
        try:
            r = await self.client.get(url, params={**auth, **params})
            r.raise_for_status()
            return r.json().get("subsonic-response", {})
        except Exception as exc:
            log.warning("Navidrome call %s failed: %s", endpoint, exc)
            return {}

    async def validate_user(self, user_auth: dict) -> bool:
        """Ping Navidrome with user_auth; returns True if credentials are valid."""
        resp = await self.call("ping", user_auth=user_auth)
        return resp.get("status") == "ok"

    # ── raw passthrough (binary: stream, getCoverArt, download) ──────────────

    async def stream_endpoint(
        self,
        endpoint: str,
        params: dict,
        user_auth: Optional[dict] = None,
    ) -> httpx.Response:
        endpoint = endpoint.lstrip("/")
        if not endpoint.endswith(".view"):
            endpoint = endpoint + ".view"

        clean = {k: v for k, v in params.items() if k not in ("u","t","s","p","v","c","f")}
        auth  = _wrap(user_auth) if user_auth else _admin_auth()

        req  = self.client.build_request("GET", f"{_BASE_URL}/rest/{endpoint}",
                                         params={**auth, **clean})
        return await self.client.send(req, stream=True)

    # ── admin-only ────────────────────────────────────────────────────────────

    async def trigger_scan(self) -> None:
        await self.call("startScan")
