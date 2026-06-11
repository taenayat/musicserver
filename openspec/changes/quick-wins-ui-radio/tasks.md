## 1. Radio multi-seed (backend)

- [x] 1.1 In `deezer_api.py`, ensure helpers exist to resolve a seed's artist: reuse `get_track` (read `artist.id`) and `get_album` (read `artist.id`).
- [x] 1.2 In `radio.py:get_radio_tracks`, change the `track` branch to resolve the track's artist id then call `get_artist_radio`.
- [x] 1.3 In `radio.py:get_radio_tracks`, change the `album` branch to resolve the album's artist id then call `get_artist_radio` (drop the "first track → track radio" path).
- [x] 1.4 Remove or stop using the dead `get_track_radio` helper.
- [x] 1.5 Verify `start_radio` raises a clear "No radio tracks found" error only when no artist/related tracks resolve.
- [ ] 1.6 Manually test: start radio from a track seed and an album seed; confirm tracks download and the playlist fills.

## 2. YouTube source toggle (frontend)

- [x] 2.1 In `pages/SearchPage.jsx`, add `source` state (`'deezer' | 'youtube'`), defaulting to `'deezer'`.
- [x] 2.2 Make the search effect dispatch to `api.search` or `api.searchYoutube` based on `source`; store results in a single active-results structure.
- [x] 2.3 Replace the disabled-until-typed YouTube button with an always-enabled source toggle (only offering YouTube when `health.ytdlp_enabled`).
- [x] 2.4 Render results so the active source's results replace the other's (no appended YouTube section).
- [x] 2.5 Re-run the query when the source toggles with text already present.
- [ ] 2.6 Manually test: type a query, toggle to YouTube (results swap), toggle back to Deezer.

## 3. Radio seed picker layout (frontend)

- [x] 3.1 In `pages/RadioPage.jsx` `SeedModal`, restructure so `SearchBar` is in a non-scrolling pinned header and results live in a `flex-1 overflow-y-auto` body.
- [ ] 3.2 Confirm the input stays fixed while results load and when the keyboard opens.
- [ ] 3.3 Confirm seed selection + confirm step still work.

## 4. Admin RAM sparkline (frontend)

- [x] 4.1 In `pages/AdminPage.jsx` Overview, add a second `Sparkline` with `accessor={(p) => p.ram_mb}` beside the CPU sparkline, under the same `pts.length > 1` guard, labeled "RAM".
- [ ] 4.2 Confirm it renders with real metrics history.

## 5. Build & verify

- [ ] 5.1 Rebuild the frontend bundle (`npm run build`) and the gateway image.
- [ ] 5.2 Smoke-test all four changes end to end.
