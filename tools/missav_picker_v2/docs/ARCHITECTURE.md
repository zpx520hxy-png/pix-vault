# MissAV Picker V2 Architecture

## Goals

- Keep `tools/missav_picker/` untouched as the stable legacy tool.
- Rebuild the tool in `tools/missav_picker_v2/` with clearer backend/frontend boundaries.
- Make playback, cache, and trending logic easier to debug and evolve.

## Runtime Ports

- Legacy: `http://localhost:8699`
- V2: `http://localhost:8700`

## Backend Layout

`run.py` starts `server.app.run()`.

### `server/config.py`

- Port / proxy / cache directories / constants
- `MISSAV_PICKER_PORT`
- `MISSAV_PICKER_PROXY`
- cache size and TTL constants

### `server/cache.py`

- image/play counters
- browser hls map read/write
- L1 in-memory cache helpers
- L2 disk cache size + LRU eviction

### `server/img_proxy.py`

- `/img/...` proxy
- disk image cache
- jpeg/png/gif/webp type detection

### `server/play_proxy.py`

- `/play/<code>/playlist.m3u8`
- `/play/<code>/<segment>.ts`
- async play request/status state machine
- browser-hls-map first, then cached meta, then remote fetch fallback
- segment prefetch after playlist ready

### `server/trending.py`

- missav/jable trending fetch + parse
- local fallback when upstream is not available
- cached by `(source, period)`

### `server/sync_state.py`

- shared sync state file read/write
- `jable_codes` helper for browser-assisted mapping

### `server/prewarm.py`

- collect prewarm targets
- currently: jable favorites + history + top-20 local trending
- background daemon
- writes `.cache_plan.json`

### `server/sources.py`

- `VideoSource` abstract base
- `JableSource`
- `MissavSource`

### `server/app.py`

- HTTP handler/router
- static file serving
- `health`, `stats`, `cache_plan`, `trending`, `img`, `play`, `sync_state`

## Frontend Layout

The frontend was split from one giant inline script into classic layered files.

Loaded in order:

1. `js/core.js`
2. `js/filters.js`
3. `js/roll.js`
4. `js/render.js`
5. `js/history.js`
6. `js/favorites.js`
7. `js/persist.js`
8. `js/browse.js`
9. `js/init.js`
10. `js/trending.js`
11. `js/events.js`
12. `app.js`

This is intentionally **classic script layering**, not ES Modules, because the codebase still relies heavily on shared globals and immediate event binding.

## Current Playback Model

### Jable

- cover click
  - calls `/play/<code>/request`
  - polls `/play/<code>/status`
  - once `ready`, runs `initJplayer(v)`
- if `failed` / `not_found`, UI shows a clear message instead of infinite spinner

### MissAV

- result card stays external-link based
- trending hover preview uses `/trend_preview/missav/<code>.mp4`

## Cache Model

### Images

- server-side disk cache in `.img_cache/`
- browser cache via `Cache-Control: max-age=604800`
- `Last-Modified` + 304 revalidation

### Playback

- server-side disk cache in `.img_cache/play/<code>/`
- optional browser-derived hls map in `.browser_hls_map.json`
- prewarm status in `.cache_plan.json`

## Known Trade-offs

- frontend is split, but still global-state driven
- async playback is wired, but prewarm only helps videos whose hls chain is discoverable
- Jable/Cloudflare still limits full automation of every uncached video
- `render.js` still contains both result rendering and player logic; future split can move player code into its own loaded script if needed

## Recommended Next Steps

1. split `render.js` into result + player runtime without changing global load order
2. move sync polling and cache banner into a dedicated runtime controller
3. add tests around trending fallback and play status transitions
4. if Jable automation becomes reliable, upgrade prewarm from metadata-level to full playlist-level warming
