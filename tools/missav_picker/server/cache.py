import json
import time
import os
import threading
from pathlib import Path
from collections import OrderedDict

from .config import (
    CACHE_DIR,
    CACHE_MAX_BYTES,
    PLAY_CACHE_MAX_BYTES,
    PLAY_CACHE_DIR,
    BROWSER_HLS_MAP_FILE,
)

_HIT = 0
_MISS = 0
_FAIL = 0
_PLAY = 0
_PLAY_FAIL = 0

_L1_MAX = 50
_L1_CACHE = OrderedDict()
_L1_LOCK = threading.Lock()


def inc_hit():
    global _HIT
    _HIT += 1


def inc_miss():
    global _MISS
    _MISS += 1


def inc_fail():
    global _FAIL
    _FAIL += 1


def inc_play():
    global _PLAY
    _PLAY += 1


def inc_play_fail():
    global _PLAY_FAIL
    _PLAY_FAIL += 1


def get_counters():
    return {
        "hit": _HIT,
        "miss": _MISS,
        "fail": _FAIL,
        "play": _PLAY,
        "play_fail": _PLAY_FAIL,
    }


def l1_get(key):
    with _L1_LOCK:
        if key in _L1_CACHE:
            _L1_CACHE.move_to_end(key)
            return _L1_CACHE[key]
    return None


def l1_set(key, value):
    with _L1_LOCK:
        _L1_CACHE[key] = value
        _L1_CACHE.move_to_end(key)
        while len(_L1_CACHE) > _L1_MAX:
            _L1_CACHE.popitem(last=False)


def l1_invalidate(key):
    with _L1_LOCK:
        _L1_CACHE.pop(key, None)


def read_browser_hls_map():
    try:
        if BROWSER_HLS_MAP_FILE.is_file():
            data = json.loads(BROWSER_HLS_MAP_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def write_browser_hls_map(data):
    BROWSER_HLS_MAP_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def upsert_browser_hls(code, hls_url):
    data = read_browser_hls_map()
    data[code.lower().strip()] = hls_url.strip()
    write_browser_hls_map(data)
    return data


def get_cache_size(subdir=None):
    root = CACHE_DIR / subdir if subdir else CACHE_DIR
    if not root.is_dir():
        return 0, 0
    files = [p for p in root.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    return len(files), total


def evict_cache(max_bytes=CACHE_MAX_BYTES, subdir=None):
    root = CACHE_DIR / subdir if subdir else CACHE_DIR
    if not root.is_dir():
        return
    try:
        files = [p for p in root.rglob("*") if p.is_file()]
        total = sum(p.stat().st_size for p in files)
    except OSError:
        return
    if total <= max_bytes:
        return
    files.sort(key=lambda p: p.stat().st_mtime)
    target = total - int(max_bytes * 0.9)
    freed = 0
    for p in files:
        if freed >= target:
            break
        try:
            sz = p.stat().st_size
            p.unlink()
            freed += sz
        except OSError:
            pass


def evict_play_cache():
    evict_cache(PLAY_CACHE_MAX_BYTES, "play")


def evict_img_cache():
    evict_cache(CACHE_MAX_BYTES)
