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
        self._admin_jwt: Optional[str] = None

    async def close(self):
        await self.client.aclose()

    # ── admin JWT (Navidrome's native REST API, not Subsonic) ────────────────

    async def get_admin_jwt(self, force: bool = False) -> str:
        """Log in as the Navidrome admin and cache the JWT. Refresh on demand."""
        if self._admin_jwt and not force:
            return self._admin_jwt
        r = await self.client.post(
            f"{_BASE_URL}/auth/login",
            json={"username": _ADMIN_USER, "password": _ADMIN_PASS},
        )
        r.raise_for_status()
        data = r.json()
        token = data.get("token") or data.get("jwt") or ""
        if not token:
            raise RuntimeError("Navidrome login returned no token")
        self._admin_jwt = token
        return token

    async def _admin_request(self, method: str, path: str, **kw) -> httpx.Response:
        """Issue a Navidrome REST request with the admin JWT, retrying once on 401."""
        for attempt in (1, 2):
            jwt = await self.get_admin_jwt(force=(attempt == 2))
            headers = {**kw.pop("headers", {}), "Authorization": f"Bearer {jwt}",
                       "X-ND-Authorization": f"Bearer {jwt}"}
            r = await self.client.request(method, f"{_BASE_URL}{path}",
                                          headers=headers, **kw)
            if r.status_code == 401 and attempt == 1:
                self._admin_jwt = None
                continue
            return r
        return r  # type: ignore[return-value]

    async def create_nav_user(self, username: str, password: str,
                              is_admin: bool = False) -> dict:
        r = await self._admin_request(
            "POST", "/api/user",
            json={"userName": username, "name": username, "password": password,
                  "isAdmin": is_admin, "email": ""},
        )
        r.raise_for_status()
        return r.json()

    async def update_nav_user(self, nav_id: str, password: Optional[str] = None,
                              is_admin: Optional[bool] = None) -> None:
        body: dict = {}
        if password is not None:
            body["password"] = password
        if is_admin is not None:
            body["isAdmin"] = is_admin
        if not body:
            return
        r = await self._admin_request("PUT", f"/api/user/{nav_id}", json=body)
        r.raise_for_status()

    async def delete_nav_user(self, nav_id: str) -> None:
        r = await self._admin_request("DELETE", f"/api/user/{nav_id}")
        if r.status_code not in (200, 204, 404):
            r.raise_for_status()

    async def list_nav_users(self) -> list:
        r = await self._admin_request("GET", "/api/user")
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else data.get("data", [])

    async def server_stats(self) -> dict:
        """Best-effort song/artist/album counts + last scan via getScanStatus."""
        try:
            scan = await self.call("getScanStatus")
            ss = scan.get("scanStatus", {})
            return {
                "reachable": bool(scan),
                "song_count": ss.get("count", 0),
                "folder_count": ss.get("folderCount", 0),
                "last_scan": ss.get("lastScan"),
                "scanning": ss.get("scanning", False),
            }
        except Exception:
            return {"reachable": False}

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

    # ── Subsonic playlists (per-user auth) ───────────────────────────────────

    async def create_playlist(self, name: str, user_auth: dict) -> Optional[str]:
        resp = await self.call("createPlaylist", user_auth=user_auth, name=name)
        pl = resp.get("playlist", {})
        return pl.get("id")

    async def resolve_song_id(self, title: str, artist: str,
                              user_auth: dict) -> Optional[str]:
        """Find Navidrome's own song id for a (title, artist) via search3."""
        resp = await self.call("search3", user_auth=user_auth, query=title,
                               songCount=5, artistCount=0, albumCount=0)
        songs = resp.get("searchResult3", {}).get("song", [])
        artist_l = (artist or "").lower()
        for s in songs:
            if artist_l and artist_l in (s.get("artist", "").lower()):
                return s.get("id")
        return songs[0].get("id") if songs else None

    async def add_songs_to_playlist(self, playlist_id: str, song_ids: list,
                                    user_auth: dict) -> None:
        if not song_ids:
            return
        params = {"playlistId": playlist_id}
        # Subsonic accepts repeated songIdToAdd params; httpx encodes list values.
        params["songIdToAdd"] = song_ids
        await self.call("updatePlaylist", user_auth=user_auth, **params)

    async def delete_playlist(self, playlist_id: str, user_auth: dict) -> None:
        await self.call("deletePlaylist", user_auth=user_auth, id=playlist_id)

    async def get_starred2(self, user_auth: Optional[dict] = None) -> dict:
        resp = await self.call("getStarred2", user_auth=user_auth)
        return resp.get("starred2", {})

    # ── admin-only ────────────────────────────────────────────────────────────

    async def trigger_scan(self) -> bool:
        """Trigger a Navidrome library scan.

        Returns True if Navidrome accepted the request. Unlike `call()`, this
        does not silently swallow failures — it logs them — so fire-and-forget
        callers still surface a problem in the log, and the admin endpoint can
        report real success/failure.
        """
        endpoint = "startScan.view"
        url = f"{_BASE_URL}/rest/{endpoint}"
        try:
            r = await self.client.get(url, params=_admin_auth())
            r.raise_for_status()
            resp = r.json().get("subsonic-response", {})
            ok = resp.get("status") == "ok"
            if not ok:
                log.warning("Navidrome startScan returned: %s", resp)
            return ok
        except Exception as exc:
            log.warning("Navidrome startScan failed: %s", exc)
            return False
