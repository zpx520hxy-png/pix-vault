import json
import time
import os
import re
import urllib.request
import urllib.error
from pathlib import Path

from .config import ROOT, CACHE_DIR, CACHE_FAIL_TTL, CACHE_OK_TTL, proxy_kwargs
from .cache import inc_hit, inc_miss, inc_fail, evict_img_cache

_CREQ_SESSION = None
_CREQ_LOCK = None


def _get_creq():
    global _CREQ_SESSION, _CREQ_LOCK
    if _CREQ_SESSION:
        return _CREQ_SESSION
    if _CREQ_LOCK is None:
        import threading

        _CREQ_LOCK = threading.Lock()
    with _CREQ_LOCK:
        if _CREQ_SESSION:
            return _CREQ_SESSION
        try:
            from curl_cffi import requests as creq

            _CREQ_SESSION = creq.Session()
        except ImportError:
            _CREQ_SESSION = False
    return _CREQ_SESSION


_CONTENT_TYPES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"GIF8": "image/gif",
    b"RIFF": "image/webp",
}


def _detect_ct(data):
    for magic, ct in _CONTENT_TYPES.items():
        if data[:4] == magic[:4]:
            return ct
    return "image/jpeg"


def proxy_img(path_remainder):
    cache_key = path_remainder.replace("/", "_")
    cache_path = CACHE_DIR / cache_key
    neg_path = cache_path.with_suffix(".fail")
    if neg_path.is_file() and (time.time() - neg_path.stat().st_mtime) < CACHE_FAIL_TTL:
        return None, "neg_cache"
    if (
        cache_path.is_file()
        and (time.time() - cache_path.stat().st_mtime) < CACHE_OK_TTL
    ):
        data = cache_path.read_bytes()
        ct = _detect_ct(data)
        inc_hit()
        return (data, ct), "cache"
    inc_miss()
    domain = (
        path_remainder.split("/", 1)[0] if "/" in path_remainder else path_remainder
    )
    upstream = "https://" + path_remainder
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "image/*,video/*",
    }
    data = b""
    ct = "image/jpeg"
    if "jable.tv" in domain:
        creq = _get_creq()
        if creq:
            try:
                r = creq.get(
                    upstream,
                    impersonate="chrome",
                    timeout=15,
                    headers={**headers, "Referer": "https://jable.tv/"},
                    **proxy_kwargs(),
                )
                if r.status_code != 200:
                    raise OSError(f"image status {r.status_code}")
                data = r.content
                ct = r.headers.get("Content-Type", "image/jpeg")
            except Exception:
                pass
    if not data:
        try:
            req = urllib.request.Request(upstream, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
                ct = resp.headers.get("Content-Type", "image/jpeg")
        except Exception:
            inc_fail()
            try:
                neg_path.parent.mkdir(parents=True, exist_ok=True)
                neg_path.touch()
            except OSError:
                pass
            return None, "fetch_error"
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(data)
    except OSError:
        pass
    evict_img_cache()
    return (data, ct), "fetched"
