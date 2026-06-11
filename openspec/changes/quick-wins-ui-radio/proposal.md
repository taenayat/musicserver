## Why

Four small, high-visibility issues degrade day-to-day use of the gateway: radio only works for artist seeds (track/album seeds silently fail), the YouTube search button is a dead greyed-out control instead of a usable source switch, the radio seed picker's search box drifts as you type, and the admin page graphs CPU but not RAM even though RAM is already collected. All four are low-risk and mostly frontend, so they ship together as quick wins.

## What Changes

- **Radio seeds for tracks and albums** — track and album seeds currently route through a non-existent Deezer `/track/{id}/radio` endpoint and return no tracks. Resolve the seed's artist and use the working artist-radio endpoint so all three seed types produce a station.
- **YouTube search becomes a source toggle** — replace the disabled-until-typed one-shot YouTube button with a Deezer ↔ YouTube source toggle. Activating YouTube routes the search bar to YouTube and shows its results in place of Deezer's. **BREAKING** (UX only): YouTube results no longer append below Deezer results.
- **Radio seed picker search bar stays pinned** — the seed picker's search input is pinned at the top of its panel and results scroll beneath it, matching the Search tab.
- **RAM monitoring on the admin page** — add a RAM sparkline next to the existing CPU sparkline using metrics already collected.

## Capabilities

### New Capabilities
- `radio-multi-seed`: radio stations can be started from track, album, or artist seeds.
- `youtube-search-mode`: search has a Deezer/YouTube source toggle that swaps which provider the query hits and which results are shown.
- `radio-seed-picker-ui`: the radio seed picker keeps its search field pinned while results scroll.
- `admin-resource-monitoring`: the admin overview shows RAM usage history alongside CPU.

### Modified Capabilities
- None (no pre-existing specs).

## Impact

- Backend: `deezer_api.py` (artist resolution for track/album radio), `radio.py` (`get_radio_tracks` seed handling). No new endpoints, no schema changes.
- Frontend: `pages/SearchPage.jsx` (source toggle), `pages/RadioPage.jsx` (seed picker layout), `pages/AdminPage.jsx` (RAM sparkline). No API contract changes — `/api/admin/metrics` already returns `ram_mb`.
