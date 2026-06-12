# Music Gateway

A self-hosted **music server with a web UI**: browse and download from Deezer
(or YouTube), and your library is served to phones and desktops through
[Navidrome](https://www.navidrome.org/) over the Subsonic API.

You search Deezer, preview tracks, and queue downloads; the gateway fetches them
with deemix (or yt-dlp), embeds cover art, writes synced-lyrics `.lrc` sidecars,
and drops the files into your `/music` library. Navidrome scans that library so
any Subsonic client (e.g. [Symfonium](https://symfonium.app/)) can play it.

```
  [Symfonium / Subsonic app] ──> [Navidrome :4533] <──scan trigger── [Gateway :8080]
                                        ▲                                  │
                                   /music volume <──── downloads ──────────┤
                                                                           │
  [Browser / PWA] ──REST API────────────────────────────────────────> [Gateway :8080]
                                                              ┌────────────┼────────────┐
                                                        [Deezer API]   [deemix]   [yt-dlp]
```

The gateway does **not** proxy Subsonic — Symfonium connects to Navidrome
directly. The gateway is the browse/download/manage side, driven by its own
React web app.

---

## Features

- **Search** Deezer for artists, albums, and tracks, with a Deezer ↔ YouTube
  source toggle.
- **Browse** an artist's discography and top tracks, or an album's track list.
- **Preview** any track (30-second clip) in a bottom mini-player.
- **Download** a track or whole album — queued in SQLite, fetched by deemix or
  yt-dlp, with **embedded cover art** and **`.lrc` lyrics sidecars** so art and
  lyrics show up in your player.
- **Radio** — start an endless station from any track, album, or artist seed.
- **Lyrics** — in-app synced-lyrics overlay (lrclib), plus sidecars on disk.
- **Multi-user accounts** — each gateway account is backed by a Navidrome
  account, so the same login plays back in Symfonium.
- **Admin panel** — manage users, trigger/observe Navidrome scans, backfill
  missing art and lyrics, run the album-art sync tool, and watch CPU/RAM.
- **Telegram backup** (optional) — mirror downloads to a private channel, and
  import audio sent to the bot back into the library.
- **Hot cache** (optional) — keep a bounded working set on disk and offload the
  rest to Telegram, recalling on demand.
- Installable **PWA** (add to home screen, offline app shell).

---

## Repository layout

This repo is the gateway service; `docker compose up` also starts a Navidrome
container to serve the library.

```
.
├── docker-compose.yml         ← gateway + navidrome
├── env.example                ← copy to .env and fill in
├── Dockerfile                 ← multi-stage: node frontend build + python runtime
├── requirements.txt
├── main.py                    ← FastAPI REST API + static frontend host
├── auth.py                    ← sessions, password hashing, Navidrome-backed users
├── db.py                      ← SQLite (aiosqlite): users, queue, library, lyrics…
├── deezer_api.py              ← Deezer client + normalizers
├── downloader.py              ← deemix/yt-dlp worker, SQLite-backed queue
├── ytdlp.py                   ← YouTube search + download (cookies, deno/EJS)
├── artwork.py / lyrics.py     ← cover-art embedding, .lrc sidecars
├── radio.py                   ← seed → station generation
├── library.py                 ← library indexing + missing-art detection
├── telegram.py                ← Telegram backup + inbound ingest
├── cache.py                   ← hot-cache eviction/recall
├── navidrome.py               ← Navidrome client (scan trigger + status)
├── tests/                     ← pytest suite
└── frontend/                  ← React + Vite + Tailwind PWA (built into dist/)
```

A `music/` and `data/` directory are created next to the compose file at runtime
(bind mounts) and are gitignored.

---

## Accounts & authentication

The web app and REST API use **per-user accounts**. Each `/api/*` request carries
a session token (`Authorization: Bearer <token>`) issued by `POST /api/auth/login`.

- On **first run** (no users yet), the web app shows a **create-admin** screen.
  The first account becomes the admin.
- Each gateway account is mirrored to a **Navidrome account**, so the same
  username/password logs into Symfonium for playback. Manage all accounts from
  the gateway admin panel — don't change passwords directly in Navidrome.
- `GATEWAY_SECRET_KEY` is a Fernet key the gateway uses to encrypt stored
  Navidrome passwords; set it once and keep it stable.

---

## Setup

### 1. Configure `.env`

```bash
cp env.example .env
nano .env
```

Key values (see `env.example` for the full annotated list):

- `NAVIDROME_ADMIN_USER` / `NAVIDROME_ADMIN_PASS` — Navidrome admin account the
  gateway uses to trigger scans and manage users.
- `DEEZER_ARL` — your Deezer `arl` browser cookie. Expires periodically; the
  gateway logs `Deezer ARL INVALID` on startup when it needs refreshing.
- `GATEWAY_SECRET_KEY` — generate one:
  `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `DEEMIX_BITRATE` — `320` (default), `128`, or `FLAC`. Falls back automatically.
- Optional: Telegram, hot cache, radio, lyrics, and YouTube-cookie settings.

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

### 4. Create the admin account

Open `http://<host>:4040` and complete the **create-admin** screen on first run.
This also provisions the matching Navidrome account.

### 5. Connect your clients

- **Web app:** `http://<host>:4040` — log in with your account.
- **Symfonium / Subsonic:** point it **directly at Navidrome**
  (`http://<host>:4533`) using your account. Expose Navidrome's port or put it
  behind a reverse proxy. See [CONNECTING.md](CONNECTING.md) for details,
  including the background-sync setting that makes new downloads appear
  automatically.

---

## REST API (selected)

All routes require `Authorization: Bearer <token>` except `GET /health` and the
static files. Admin routes additionally require an admin account.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/login` · `/logout` · `GET /me` | Session auth |
| GET | `/api/search?q=&limit=` · `/api/search/youtube` | Search Deezer / YouTube |
| GET | `/api/artist/{id}` · `/api/album/{id}` | Browse |
| GET | `/api/preview/{track_id}` | 30s preview (audio/mpeg) |
| POST | `/api/download` | Queue a `track`/`album` download |
| GET/DELETE | `/api/queue` · `/api/queue/{id}` | Download queue |
| GET | `/api/library/stats` · `/api/lyrics` · `/api/cover` | Library / lyrics / cover proxy |
| POST/GET | `/api/radio` · `/api/radio/{id}/like` · `/dismiss` | Radio stations |
| GET | `/api/cache/status` · POST `/api/cache/recall` | Hot cache |
| — | `/api/admin/users`, `/admin/scan`, `/admin/art/*`, `/admin/lyrics/backfill`, `/admin/metrics` | Admin |

---

## Development

**Backend tests:**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest pytest-asyncio
.venv/bin/python -m pytest
```

**Frontend dev server** (proxies `/api` + `/health` to a backend on `:4040`):

```bash
cd frontend
npm install
npm run dev
```

The production image builds the frontend itself (`npm run build` → `dist/`) and
FastAPI serves it; there is no separate frontend container.

---

## Notes & limitations

- **Symfonium talks to Navidrome directly.** The gateway has no Subsonic routes.
  Make sure Navidrome's `4533` is reachable — expose its port in
  `docker-compose.yml` or front it with a reverse proxy (e.g. Caddy for HTTPS).
- **No artist-level downloads** — download albums or individual tracks.
- **Previews are 30s** — that's what Deezer's public API provides.
- **YouTube downloads** may need a `cookies.txt` (`YTDLP_COOKIES_FILE`) to get
  past YouTube's datacenter-IP bot wall; search works without it.
- **Pending downloads survive restarts** (SQLite queue); an interrupted download
  is reset to pending and retried on the next start.
- **No HTTPS** out of the box — put a reverse proxy in front for TLS.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Stuck on login / "Invalid credentials" | Use a valid account; on a fresh install the first-run screen creates the admin |
| `Deezer ARL INVALID` in logs | Grab a fresh `arl` cookie and restart |
| YouTube downloads fail ("only images available" / bot wall) | Set `YTDLP_COOKIES_FILE` to an exported `cookies.txt`; rebuild |
| Downloads succeed but don't appear | Wait for Navidrome's scan (≤1 min) or trigger it from the admin panel |
| New tracks don't show in Symfonium | Enable Symfonium's background sync — see [CONNECTING.md](CONNECTING.md) |
| `deemix CLI not found` | Rebuild the image: `docker compose build --no-cache gateway` |
