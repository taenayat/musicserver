# Connecting to the Music Gateway stack

Both services are running on the VPS (`167.233.30.70`):

| Service | URL | Who connects | Auth |
|---|---|---|---|
| Gateway (web app / API) | `http://167.233.30.70:4040` | Your browser / phone browser | `GATEWAY_API_KEY` |
| Navidrome (Subsonic) | `http://167.233.30.70:4533` | Symfonium, other Subsonic apps | Navidrome account |

> The gateway downloads music into `/music`; Navidrome serves that library. They
> are two separate connections — the gateway no longer proxies Subsonic.

---

## A. The web app (browse + download)

1. On any device, open **`http://167.233.30.70:4040`**.
2. You'll see the login screen. Paste the API key:
   ```
   cc7e6b8863ce9005fc0a41e7adb6450cf5334f360e51979c
   ```
   (This is `GATEWAY_API_KEY` in `/opt/music/.env`. It's stored in the browser, so
   you only enter it once per device.)
3. Use the **Search** tab to find artists/albums/tracks. Tap ▶ to preview (30s),
   tap ↓ to download a track, or open an album and "Download All".
4. The **Queue** tab shows download progress (pending → downloading → done).
   Once an item is **done**, deemix has written it to `/music` and Navidrome has
   been told to rescan — it appears in your library within ~1 minute.

---

## B. Symfonium (playback) — connects to Navidrome directly

1. In Symfonium: **Settings → Library → Add → Subsonic / Navidrome**.
2. Fill in:
   - **Server / URL:** `http://167.233.30.70:4533`
   - **Username:** `admin`  *(your `NAVIDROME_ADMIN_USER`)*
   - **Password:** `%ELc!hp5`  *(your `NAVIDROME_ADMIN_PASS`)*
3. Save and let it sync. Everything in `/music` (including freshly downloaded
   tracks) plays in full, with scrobbling/starring handled by Navidrome.

> First time only: if Navidrome's admin account isn't created yet, open
> `http://167.233.30.70:4533` in a browser and create it with **exactly** these
> same credentials.

Any other Subsonic client (DSub, play:Sub, Symfonium, the Navidrome web UI at
`:4533`) works the same way — they all talk to Navidrome, not the gateway.

---

## Typical flow

```
Phone browser → :4040 web app → search "Daft Punk" → Download All on an album
        │
        ▼
   gateway queues it → deemix downloads into /music → Navidrome rescans
        │
        ▼
Symfonium (→ :4533) → library refresh → play the new album in full quality
```

---

## C. Add the web app to your Android home screen

Over plain HTTP this is a **home-screen shortcut** (not a full standalone PWA —
that needs HTTPS), but it gives you a tappable app icon that stays logged in.

**Chrome (Android):**
1. Open `http://167.233.30.70:4040` and log in with the API key once.
2. Tap **⋮** (top-right) → **Add to Home screen**.
3. Name it "Music Gateway" → **Add** → **Add automatically**.
4. The gradient music-note icon appears on your home screen. Tapping it opens
   the app (inside Chrome — you'll see a thin address bar, since the site is HTTP).

**Firefox / Samsung Internet (Android):** menu → **Add page to → Home screen**
(Samsung Internet) or menu → **Install / Add to Home screen** (Firefox).

Notes:
- The API key is saved in that browser's storage, so the shortcut stays logged
  in until you clear browsing data.
- Want a true full-screen app (no address bar) + offline + an installable `.apk`?
  That requires HTTPS — point a domain at this host (Caddy auto-HTTPS) or run a
  tunnel, then the browser's **Install app** prompt and Bubblewrap/TWA become
  available. The PWA manifest + service worker are already built and waiting.

## Security note (plain HTTP)

Both ports are currently served over **plain HTTP on a public IP**. The API key
and Navidrome password travel unencrypted. For anything beyond testing, put a
reverse proxy with HTTPS in front (see the Android / PWA section — the same
HTTPS setup is what makes the web app installable as an app).
