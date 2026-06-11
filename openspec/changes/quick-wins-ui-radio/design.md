## Context

The gateway is a FastAPI backend + React (Vite/Tailwind) frontend wrapping Navidrome and Deezer/YouTube downloads. These four fixes touch the Deezer client, the radio module, and three frontend pages. They share nothing except being small and low-risk, so they are bundled to ship together.

Current relevant state:
- `radio.py:get_radio_tracks` branches on seed type. The `track` and `album` branches call `deezer.get_track_radio(...)`, which hits `/track/{id}/radio` — not a real Deezer public endpoint — so they return `[]` and `start_radio` raises "No radio tracks found".
- `SearchPage.jsx` renders a round YouTube button gated by `health.ytdlp_enabled` and `disabled={!query.trim() || ytLoading}`. On success it appends a "YouTube Music" section below Deezer results.
- `RadioPage.jsx`'s `SeedModal` is a bottom-anchored sheet (`items-end`, `animate-slide-up`, `max-h-[85vh] overflow-y-auto`) with `SearchBar` as the first scrolling child.
- `AdminPage.jsx` Overview renders a single CPU `Sparkline` from `metrics.points`. The metrics rows already include `ram_mb` (db `metrics` table) and `cpu_percent`.

## Goals / Non-Goals

**Goals:**
- Make radio work for track and album seeds via artist resolution.
- Turn the YouTube control into a Deezer↔YouTube source toggle that swaps results.
- Pin the radio seed picker's search bar.
- Add a RAM sparkline to the admin overview.

**Non-Goals:**
- No new Deezer "track radio" emulation beyond artist resolution (no genre/BPM matching).
- No change to the YouTube download path or yt-dlp version in this change (a stale-yt-dlp verification is noted as a risk, handled separately if results are empty).
- No new metrics fields or API changes.

## Decisions

**Radio: resolve seed → artist, then artist radio.**
In `get_radio_tracks`, for `track` seeds call `deezer.get_track(seed_id)` and read `artist.id`; for `album` seeds call `deezer.get_album(seed_id)` and read `artist.id`. Then call `get_artist_radio(artist_id, ...)`. Keep the existing dedupe + `is_in_library` filtering. Rationale: `/artist/{id}/radio` is the only related-tracks endpoint Deezer actually serves; resolving through the seed's artist is the minimal correct fix. Alternative considered: Deezer chart/recommendation search by genre — rejected as heavier and lower quality than artist radio. The dead `get_track_radio` helper can be removed or left unused; prefer removing to avoid future foot-guns.

**YouTube: client-side source state, not a new endpoint.**
Add a `source` state (`'deezer' | 'youtube'`) in `SearchPage`. The debounced search effect dispatches to `api.search` or `api.searchYoutube` based on `source`. The toggle button sets `source` and is never disabled. Results render from a single active-results structure so YouTube replaces Deezer. Rationale: both endpoints already exist; this is pure view/state wiring. Alternative considered: a separate route/tab — rejected per user preference for an in-place toggle.

**Radio seed picker: pinned header layout.**
Restructure `SeedModal` so the `SearchBar` sits in a non-scrolling header and only the results list scrolls (e.g. a flex column with a `shrink-0` header and a `flex-1 overflow-y-auto` body, or `sticky top-0` on the search row). Mirror the Search tab's structure. Rationale: keeps the input stable under keyboard/result changes.

**RAM sparkline: reuse existing component and data.**
Add a second `Sparkline` with `accessor={(p) => p.ram_mb}` beside the CPU one, under the same `pts.length > 1` guard. Rationale: data and component already exist; one small JSX addition.

## Risks / Trade-offs

- **yt-dlp may still return no results once the toggle works** → the visible bug (dead button) is fixed regardless; if YouTube returns empty, that's a separate backend staleness issue tracked outside this change. Verify during implementation by running a real YouTube query.
- **Album/track artist resolution adds one extra Deezer call per radio start** → negligible; Deezer client already caches responses for 5 minutes.
- **Source toggle changes existing behavior** (YouTube no longer appends) → intended; documented as a UX breaking change.

## Open Questions

- None blocking. Whether to fully delete `get_track_radio` vs leave it dead is an implementer's call (prefer delete).
