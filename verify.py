#!/usr/bin/env python3
"""
verify.py — end-to-end smoke test against a RUNNING gateway + Navidrome stack.

Hits the real HTTP endpoints (no mocks) to confirm auth, search, browse,
preview, cover proxy, the Navidrome scan path, and a full download lifecycle.

Usage:
    python3 verify.py                 # uses /opt/music/.env, localhost ports
    BASE=http://host:4040 NAV=http://host:4533 python3 verify.py
    python3 verify.py --no-download   # skip the real Deezer download step

Exit code 0 = all checks passed.
"""
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("BASE", "http://localhost:4040").rstrip("/")
NAV = os.environ.get("NAV", "http://localhost:4533").rstrip("/")
ENV_FILE = os.environ.get("ENV_FILE", "/opt/music/.env")
DO_DOWNLOAD = "--no-download" not in sys.argv
MUSIC_DIR = os.environ.get("MUSIC_DIR", "/opt/music/music")


def load_env(path):
    env = {}
    try:
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


env = load_env(ENV_FILE)
KEY = os.environ.get("GATEWAY_API_KEY", env.get("GATEWAY_API_KEY", ""))
NUSER = env.get("NAVIDROME_ADMIN_USER", "admin")
NPASS = env.get("NAVIDROME_ADMIN_PASS", "")
AUTH = {"Authorization": f"Bearer {KEY}"}

passed = failed = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  \033[32m✓\033[0m {msg}")


def bad(msg):
    global failed
    failed += 1
    print(f"  \033[31m✗ {msg}\033[0m")


def req(path, base=BASE, headers=None, method="GET", body=None):
    """Return (status, headers, raw_bytes). Never raises on HTTP errors."""
    url = base + path
    data = None
    h = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        h["content-type"] = "application/json"
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=30)
        return resp.status, _lower(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, _lower(e.headers), e.read()
    except Exception as e:  # connection errors etc.
        return 0, {}, str(e).encode()


def _lower(headers):
    # HTTP header names are case-insensitive; Starlette emits them lowercased.
    return {k.lower(): v for k, v in headers.items()}


def jbody(raw):
    try:
        return json.loads(raw)
    except Exception:
        return None


def section(title):
    print(f"\n\033[1m{title}\033[0m")


def music_snapshot():
    n = 0
    for _, _, files in os.walk(MUSIC_DIR):
        n += len([f for f in files if f.lower().endswith((".mp3", ".flac", ".m4a"))])
    return n


# ── Auth + health ──────────────────────────────────────────────────────────────
section("Auth & health")
s, _, raw = req("/health")
b = jbody(raw) or {}
(ok if s == 200 and b.get("status") == "ok" else bad)(f"GET /health (no key) → {s} {b}")
(ok if b.get("arl_ok") is True else bad)(f"  arl_ok = {b.get('arl_ok')} (Deezer ARL valid)")

s, _, _ = req("/health", headers={"Authorization": "Bearer wrong-key"})
(ok if s == 401 else bad)(f"GET /health (wrong key) → {s} (expect 401)")

s, _, _ = req("/health", headers=AUTH)
(ok if s == 200 else bad)(f"GET /health (correct key) → {s} (expect 200)")

s, _, _ = req("/api/queue")
(ok if s == 401 else bad)(f"GET /api/queue (no key) → {s} (expect 401)")

# ── Static UI ──────────────────────────────────────────────────────────────────
section("Static frontend")
s, _, raw = req("/")
(ok if s == 200 and b'id="root"' in raw else bad)(f"GET / serves index.html → {s}")
s, h, _ = req("/manifest.webmanifest")
(ok if s == 200 else bad)(f"GET /manifest.webmanifest → {s} ({h.get('content-type','')})")

# ── Search → browse → preview → cover ──────────────────────────────────────────
section("Search / browse / preview / cover")
s, _, raw = req("/api/search?q=" + urllib.parse.quote("daft punk") + "&limit=10", headers=AUTH)
res = jbody(raw) or {}
artists, albums, tracks = res.get("artists", []), res.get("albums", []), res.get("tracks", [])
(ok if s == 200 and (artists or albums or tracks) else bad)(
    f"GET /api/search → {s}  artists={len(artists)} albums={len(albums)} tracks={len(tracks)}"
)

artist_id = artists[0]["id"] if artists else None
album_id = albums[0]["id"] if albums else None
track = next((t for t in tracks if t.get("preview_url")), tracks[0] if tracks else None)

if artist_id:
    s, _, raw = req(f"/api/artist/{artist_id}", headers=AUTH)
    d = jbody(raw) or {}
    good = s == 200 and "artist" in d and "albums" in d and "top_tracks" in d
    (ok if good else bad)(
        f"GET /api/artist/{artist_id} → {s}  albums={len(d.get('albums', []))} top={len(d.get('top_tracks', []))}"
    )
    # albums sorted by year desc
    years = [a.get("release_year") or 0 for a in d.get("albums", [])]
    (ok if years == sorted(years, reverse=True) else bad)("  artist albums sorted by year desc")
else:
    bad("no artist in search results to browse")

if album_id:
    s, _, raw = req(f"/api/album/{album_id}", headers=AUTH)
    d = jbody(raw) or {}
    trks = d.get("tracks", [])
    good = s == 200 and "album" in d and trks and trks[0].get("track_no") == 1
    (ok if good else bad)(f"GET /api/album/{album_id} → {s}  tracks={len(trks)} (track_no enumerated)")

if track:
    s, h, raw = req(f"/api/preview/{track['id']}", headers=AUTH)
    ct = h.get("content-type", "")
    (ok if s == 200 and "audio/mpeg" in ct and len(raw) > 1000 else bad)(
        f"GET /api/preview/{track['id']} → {s} {ct} ({len(raw)} bytes)"
    )
    if track.get("cover_url"):
        s, h, raw = req("/api/cover?url=" + urllib.parse.quote(track["cover_url"]) + "&size=md", headers=AUTH)
        (ok if s == 200 and h.get("content-type", "").startswith("image/") else bad)(
            f"GET /api/cover → {s} {h.get('content-type','')} ({len(raw)} bytes)"
        )
# SSRF guard
s, _, _ = req("/api/cover?url=" + urllib.parse.quote("https://evil.example.com/x.jpg"), headers=AUTH)
(ok if s == 400 else bad)(f"GET /api/cover (non-Deezer host) → {s} (expect 400)")

# ── Navidrome reachability + auth ──────────────────────────────────────────────
section("Navidrome (direct, what Symfonium uses)")
salt = secrets.token_hex(8)
token = hashlib.md5((NPASS + salt).encode()).hexdigest()
q = urllib.parse.urlencode({"u": NUSER, "t": token, "s": salt, "v": "1.16.1", "c": "verify", "f": "json"})
s, _, raw = req(f"/rest/ping.view?{q}", base=NAV)
d = (jbody(raw) or {}).get("subsonic-response", {})
(ok if s == 200 and d.get("status") == "ok" else bad)(
    f"Navidrome /rest/ping (admin creds) → {s} status={d.get('status')}"
)

# ── Download lifecycle (real deemix fetch) ─────────────────────────────────────
section("Download queue lifecycle")
s, _, _ = req("/api/download", headers=AUTH, method="POST", body={"type": "bogus", "deezer_id": 1})
(ok if s == 400 else bad)(f"POST /api/download (bad type) → {s} (expect 400)")
s, _, _ = req("/api/queue/999999", headers=AUTH, method="DELETE")
(ok if s == 404 else bad)(f"DELETE /api/queue/999999 → {s} (expect 404)")

if DO_DOWNLOAD and track:
    before = music_snapshot()
    s, _, raw = req("/api/download", headers=AUTH, method="POST", body={
        "type": "track", "deezer_id": track["id"], "title": track["title"],
        "artist": track["artist_name"], "cover_url": track.get("cover_url"),
    })
    d = jbody(raw) or {}
    dl_id = d.get("id")
    (ok if s == 200 and d.get("status") == "pending" and dl_id else bad)(
        f"POST /api/download (track '{track['title']}') → {s} id={dl_id} status={d.get('status')}"
    )

    print(f"  …waiting for deemix to fetch (up to 120s)…")
    final = None
    for _ in range(60):
        s, _, raw = req(f"/api/queue?limit=50", headers=AUTH)
        items = (jbody(raw) or {}).get("items", [])
        row = next((i for i in items if i["id"] == dl_id), None)
        if row and row["status"] in ("done", "error"):
            final = row
            break
        time.sleep(2)

    if final and final["status"] == "done":
        ok(f"  download id={dl_id} reached status=done")
        after = music_snapshot()
        # >= because deemix won't re-download a track already present (overwriteFile='n').
        (ok if after >= before and after > 0 else bad)(
            f"  music library has the track in {MUSIC_DIR} ({before} → {after} audio files)")
        s, _, _ = req(f"/api/queue/{dl_id}", headers=AUTH, method="DELETE")
        (ok if s == 204 else bad)(f"DELETE /api/queue/{dl_id} (done item) → {s} (expect 204)")
    elif final:
        bad(f"  download id={dl_id} ended status=error: {(final.get('error_msg') or '')[:120]}")
    else:
        bad(f"  download id={dl_id} did not finish within 120s (still pending/downloading)")
elif not DO_DOWNLOAD:
    print("  (skipped real download — --no-download)")


# ── Summary ────────────────────────────────────────────────────────────────────
fail_str = f"\033[31m{failed}\033[0m" if failed else "0"
print(f"\n\033[1m{'='*48}\033[0m")
print(f"  passed: \033[32m{passed}\033[0m   failed: {fail_str}")
sys.exit(1 if failed else 0)
