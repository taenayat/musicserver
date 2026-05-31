# Music Gateway

A self-hosted **Deezer download manager with a web UI**. You browse Deezer,
preview tracks, and queue downloads; the gateway fetches them with deemix into
your `/music` library, and Navidrome serves that library to your players.

```
  [Symfonium app] ──Subsonic──> [Navidrome :4533] <──scan trigger── [Gateway :4040]
                                                                          │
  [Browser / PWA] ──REST API──────────────────────────────────────> [Gateway :4040]
                                                                          │
                                                                 ┌────────┴────────┐
                                                            [Deezer API]    [deemix CLI]
                                                                                  │
                                                                            [/music volume] → Navidrome
```

The gateway no longer proxies Subsonic. **Symfonium connects directly to
Navidrome**; the gateway is purely the browse/download side, driven by its own
React web app.

---

## What it does

- **Search** Deezer for artists, albums, and tracks.
- **Browse** an artist's discography and top tracks, or an album's track list.
- **Preview** any track (30-second clip) in a bottom mini-player.
- **Download** a track or a whole album — queued in SQLite, fetched by deemix,
  then Navidrome rescans and the file appears in your library.
- **Queue view** with live status (pending / downloading / done / error).
- Installable **PWA** (add to home screen, offline app shell).

---

## File layout

```
/opt/music/
├── docker-compose.yml
├── .env                       ← copied from env.example, filled in
├── music/                     ← downloaded files (bind-mounted)
├── data/
│   ├── deemix/                ← deemix config + .arl
│   └── gateway.db             ← SQLite queue (created on first run)
└── gateway/
    ├── Dockerfile             ← multi-stage: node build + python runtime
    ├── requirements.txt
    ├── main.py                ← FastAPI REST API + static frontend
    ├── db.py                  ← SQLite queue (aiosqlite)
    ├── auth.py                ← single-key bearer auth
    ├── deezer_api.py          ← Deezer client + normalizers
    ├── downloader.py          ← deemix worker, SQLite-backed
    ├── navidrome.py           ← Navidrome client (scan trigger)
    ├── tests/                 ← pytest suite
    └── frontend/              ← React + Vite + Tailwind PWA (built into dist/)
```

---

## Authentication

The web app and REST API are protected by **one shared key**, `GATEWAY_API_KEY`.
Every `/api/*` request must send `Authorization: Bearer <key>`. On first visit the
web app shows a login screen; enter the key once and it's stored in the browser.

This is intentionally minimal (no per-user accounts in the MVP). Navidrome keeps
its own separate user accounts for playback via Symfonium.

---

## Setup

### 1. Configure `.env`

```bash
cp env.example .env
nano .env
```

- `NAVIDROME_ADMIN_USER` / `NAVIDROME_ADMIN_PASS` — Navidrome admin account (used
  by the gateway to trigger rescans; also a valid Symfonium login).
- `DEEZER_ARL` — from Deezer's `arl` browser cookie. Expires periodically; the
  gateway logs `Deezer ARL INVALID` on startup when it needs refreshing.
- `GATEWAY_API_KEY` — generate one:
  `python3 -c "import secrets; print(secrets.token_hex(24))"`
- `DEEMIX_BITRATE` — `320` (default), `128`, or `FLAC`. Falls back automatically.

### 2. Prepare directories

```bash
mkdir -p music data/deemix
```

### 3. Launch

```bash
docker compose up -d
docker compose logs -f gateway
```

You should see the ARL check (`Deezer ARL OK` or a loud `INVALID`), then
`download worker started` and `gateway ready`.

### 4. Navidrome admin user (first run)

Create the admin account in Navidrome's web UI matching your `.env`
credentials. Navidrome runs on the internal Docker network; expose `4533`
temporarily (SSH tunnel) or via your reverse proxy to reach its UI.

### 5. Connect your clients

- **Web app:** open `http://<host>:4040`, enter the `GATEWAY_API_KEY`.
- **Symfonium:** point it **directly at Navidrome** (`http://<host>:4533`) with a
  Navidrome account — not at the gateway. (Expose Navidrome's port or put it
  behind a reverse proxy; see note below.)

---

## REST API

All routes require `Authorization: Bearer <GATEWAY_API_KEY>` except `GET /health`
and the static files.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness; validates the key if one is supplied |
| GET | `/api/search?q=&limit=` | Search artists/albums/tracks |
| GET | `/api/artist/{id}` | Artist + albums + top tracks |
| GET | `/api/album/{id}` | Album + tracks |
| GET | `/api/preview/{track_id}` | Stream the 30s preview (audio/mpeg) |
| POST | `/api/download` | Queue a `track`/`album` download |
| GET | `/api/queue?limit=` | Recent download items |
| DELETE | `/api/queue/{id}` | Remove a finished/failed item (409 if downloading) |
| GET | `/api/cover?url=&size=` | Proxy a Deezer cover image (sm/md/lg) |

---

## Development

**Backend tests:**

```bash
cd gateway
python3 -m venv .venv && .venv/bin/pip install \
  fastapi uvicorn httpx aiosqlite pytest pytest-asyncio
.venv/bin/python -m pytest          # 49 tests
```

**Frontend dev server** (proxies `/api` + `/health` to a backend on `:4040`):

```bash
cd gateway/frontend
npm install
npm run dev
```

The production image builds the frontend itself (`npm run build` → `dist/`) and
FastAPI serves it; there is no separate frontend container.

---

## Notes & limitations

- **Symfonium talks to Navidrome directly.** The gateway has no Subsonic routes.
  Make sure Navidrome's `4533` is reachable by your phone — expose its port in
  `docker-compose.yml` or front it with a reverse proxy (e.g. Caddy for HTTPS).
- **No artist-level downloads** — download albums or individual tracks.
- **Previews are 30s** — that's what Deezer's public API provides.
- **Pending downloads survive restarts** (SQLite queue). A download interrupted
  mid-flight is reset to pending and retried on the next start.
- **No HTTPS** out of the box — put a reverse proxy in front for TLS.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Web app stuck on login / "Invalid key" | Key must match `GATEWAY_API_KEY` in `.env`; rebuild if you changed it |
| `Deezer ARL INVALID` in logs | Grab a fresh `arl` cookie and restart |
| Downloads do nothing on Free accounts | Already handled (bitrate fallback on); rebuild so config is written |
| Downloads succeed but don't appear | Wait for Navidrome's scan (≤1 min) or refresh the library |
| `deemix CLI not found` | Rebuild the image: `docker compose build --no-cache gateway` |
