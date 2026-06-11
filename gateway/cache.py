"""
cache.py — hot-cache eviction + recall.

/music/ is a hot cache; every permanent file is also backed up to Telegram.
When the cache exceeds CACHE_SIZE_GB, the least-valuable backed-up files are
deleted locally (the Telegram copy is preserved) until usage drops to 80% of
the limit. Recall re-downloads a file from Telegram on demand.

Policies (CACHE_EVICTION_POLICY): lru | lfu | hybrid. Pinned tracks, radio
tracks, recently-played tracks, and tracks not yet backed up are never evicted
(enforced in db.get_evictable_tracks).
"""

import asyncio
import datetime as _dt
import logging
import os
from dataclasses import dataclass

log = logging.getLogger("cache")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class CacheConfig:
    enabled: bool
    size_gb: float
    eviction_policy: str
    pin_favorites: bool
    pin_recent_days: int
    min_play_count: int
    music_dir: str

    @classmethod
    def from_env(cls) -> "CacheConfig":
        def b(v): return os.environ.get(v, "false").lower() in ("1", "true", "yes")
        return cls(
            enabled=b("CACHE_ENABLED"),
            size_gb=float(os.environ.get("CACHE_SIZE_GB", "20")),
            eviction_policy=os.environ.get("CACHE_EVICTION_POLICY", "hybrid"),
            pin_favorites=os.environ.get("CACHE_PIN_FAVORITES", "true").lower() in ("1", "true", "yes"),
            pin_recent_days=int(os.environ.get("CACHE_PIN_RECENT_DAYS", "7")),
            min_play_count=int(os.environ.get("CACHE_MIN_PLAY_COUNT", "3")),
            music_dir=os.environ.get("MUSIC_DIR", "/music"),
        )


async def maybe_evict(db, telegram, navidrome, config: CacheConfig) -> dict:
    current_gb = await db.get_cache_size_gb()
    if current_gb <= config.size_gb:
        return {"evicted": 0, "freed_mb": 0.0, "current_gb": current_gb}

    target_gb = config.size_gb * 0.80
    to_free_mb = (current_gb - target_gb) * 1024
    freed = 0.0
    evicted = 0

    candidates = await db.get_evictable_tracks(config.eviction_policy,
                                               config.pin_recent_days)
    for track in candidates:
        if freed >= to_free_mb:
            break
        if track.get("play_count_30d", 0) >= config.min_play_count:
            continue
        if track.get("location") != "both":
            log.warning("skip evict %s: not backed up", track["file_path"])
            continue
        abs_path = os.path.join(config.music_dir, track["file_path"])
        try:
            if os.path.isfile(abs_path):
                await asyncio.to_thread(os.remove, abs_path)
            freed += track.get("file_size_mb") or 0
            evicted += 1
            await db.set_track_location(track["file_path"], "telegram")
        except Exception as exc:
            log.error("evict failed for %s: %s", track["file_path"], exc)

    if evicted:
        await navidrome.trigger_scan()
    log.info("cache evict: removed %d files, freed %.1f MB", evicted, freed)
    return {"evicted": evicted, "freed_mb": round(freed, 1), "current_gb": current_gb}


async def recall_track(db, telegram, music_dir: str, file_path: str) -> bool:
    tg = await db.get_telegram_file(file_path)
    if not tg:
        return False
    dest = os.path.join(music_dir, file_path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        await telegram.download_file(tg["file_id"], dest)
        await db.set_track_location(file_path, "both")
        return True
    except Exception as exc:
        log.error("recall failed for %s: %s", file_path, exc)
        return False


async def recall_all(db, telegram, navidrome, music_dir: str) -> int:
    cold = await db.get_cold_tracks()
    recalled = 0
    for t in cold:
        if await recall_track(db, telegram, music_dir, t["file_path"]):
            recalled += 1
    if recalled:
        await navidrome.trigger_scan()
    return recalled


async def sync_play_counts(db, navidrome, config: CacheConfig) -> None:
    try:
        starred = await navidrome.get_starred2()
        starred_ids = {s.get("id") for s in starred.get("song", []) if s.get("id")}
        if config.pin_favorites and starred_ids:
            await db.sync_pinned_from_navidrome(starred_ids)
    except Exception as exc:
        log.warning("play count / favorites sync failed: %s", exc)


async def run_cache_manager(db, telegram, navidrome, config: CacheConfig,
                            interval: int = 3600) -> None:
    while True:
        await asyncio.sleep(interval)
        if not config.enabled:
            continue
        try:
            await maybe_evict(db, telegram, navidrome, config)
            await sync_play_counts(db, navidrome, config)
        except Exception as exc:
            log.error("cache manager error: %s", exc)


async def cache_status(db, config: CacheConfig) -> dict:
    local_gb = await db.get_cache_size_gb()
    tg_stats = await db.telegram_stats()
    evictable = await db.get_evictable_tracks(config.eviction_policy,
                                              config.pin_recent_days)
    return {
        "enabled": config.enabled,
        "local_gb": local_gb,
        "limit_gb": config.size_gb,
        "telegram_files": tg_stats["backed_up_files"],
        "telegram_gb": tg_stats["total_backed_gb"],
        "evictable_count": len(evictable),
        "pinned_count": await db.count_pinned(),
        "telegram_only_count": await db.count_by_location("telegram"),
        "policy": config.eviction_policy,
    }
