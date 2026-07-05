import re
import json
import time
import os
import threading
import urllib.request
import urllib.error
from pathlib import Path
from enum import Enum

from .config import ROOT, CACHE_DIR, PLAY_CACHE_DIR, CACHE_OK_TTL, proxy_kwargs
from .cache import read_browser_hls_map, inc_play, inc_play_fail, evict_play_cache


class PlayStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
    NOT_FOUND = "not_found"


_RESOLVE_LOCKS = {}
_RESOLVE_LOCK = threading.Lock()
_RESOLVE_STATUS = {}
_RESOLVE_TS = {}


def _get_resolve_status(code):
    return _RESOLVE_STATUS.get(code, {"status": PlayStatus.PENDING, "error": "", "ts": 0})


def _set_resolve_status(code, status, error=""):
    _RESOLVE_STATUS[code] = {"status": status, "error": error, "ts": time.time()}


def _acquire_resolve_lock(code):
    with _RESOLVE_LOCK:
        if code in _RESOLVE_LOCKS:
            return False
        _RESOLVE_LOCKS[code] = threading.Event()
        return True


def _release_resolve_lock(code):
    with _RESOLVE_LOCK:
        ev = _RESOLVE_LOCKS.pop(code, None)
    if ev:
        ev.set()


def _wait_resolve_lock(code, timeout=30):
    with _RESOLVE_LOCK:
        ev = _RESOLVE_LOCKS.get(code)
    if ev:
        return ev.wait(timeout)
    return True


def _async_resolve(code):
    _set_resolve_status(code, PlayStatus.PENDING)
    try:
        hls_url, source = resolve_hls_url(code)
        if not hls_url:
            _set_resolve_status(code, PlayStatus.NOT_FOUND, "hlsUrl not found")
            return
        req = urllib.request.Request(
            hls_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://jable.tv/",
                "Origin": "https://jable.tv",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        cache_root = PLAY_CACHE_DIR / code
        cache_root.mkdir(parents=True, exist_ok=True)
        m3u8_path = cache_root / "playlist.m3u8"
        meta_path = cache_root / "meta.json"
        m3u8_path.write_bytes(data)
        meta_path.write_text(hls_url, encoding="utf-8")
        _set_resolve_status(code, PlayStatus.READY)
        threading.Thread(
            target=_prefetch_ts,
            args=(code, m3u8_path, meta_path, hls_url),
            daemon=True,
        ).start()
        evict_play_cache()
    except Exception as e:
        _set_resolve_status(code, PlayStatus.FAILED, repr(e)[:120])
    finally:
        _release_resolve_lock(code)

_TS_DL_LOCKS = {}
_TS_DL_MASTER = {}
_TS_DL_LOCK = threading.Lock()
_PREFETCHED = set()
_PREFETCH_LOCK = threading.Lock()
_CREQ_SESSION = None
_CREQ_LOCK = threading.Lock()


def _get_creq():
    global _CREQ_SESSION
    if _CREQ_SESSION:
        return _CREQ_SESSION
    with _CREQ_LOCK:
        if _CREQ_SESSION:
            return _CREQ_SESSION
        try:
            from curl_cffi import requests as creq

            _CREQ_SESSION = creq.Session()
        except ImportError:
            _CREQ_SESSION = False
    return _CREQ_SESSION


def _acquire_ts_lock(key):
    with _TS_DL_LOCK:
        if key in _TS_DL_MASTER:
            ev = _TS_DL_MASTER.setdefault(key, threading.Event())
            return False
        _TS_DL_MASTER[key] = threading.Event()
        return True


def _release_ts_lock(key):
    with _TS_DL_LOCK:
        ev = _TS_DL_MASTER.pop(key, None)
    if ev:
        ev.set()


def _wait_ts_lock(key, timeout=30):
    with _TS_DL_LOCK:
        ev = _TS_DL_MASTER.get(key)
    if ev:
        return ev.wait(timeout)
    return True


def _prefetch_ts(code, m3u8_path, meta_path, hls_url):
    key = f"{code}:prefetch"
    with _PREFETCH_LOCK:
        if key in _PREFETCHED:
            return
        _PREFETCHED.add(key)
    time.sleep(15)
    try:
        meta = meta_path.read_text(encoding="utf-8").strip()
        hls_url = meta if meta.startswith("http") else hls_url
        if not hls_url:
            return
        base_url = hls_url.rsplit("/", 1)[0]
        m3u8_text = m3u8_path.read_text(encoding="utf-8")
        ts_names = re.findall(r"^([^#].+\.ts)$", m3u8_text, re.M)
        if not ts_names:
            return
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://jable.tv/",
        }
        creq = _get_creq()
        for name in ts_names[20:80]:
            ts_key = f"{code}:{name}"
            ts_cache = PLAY_CACHE_DIR / code / name
            if ts_cache.is_file():
                continue
            if not _acquire_ts_lock(ts_key):
                _wait_ts_lock(ts_key)
                continue
            try:
                if ts_cache.is_file():
                    continue
                ts_url = base_url + "/" + name
                if creq:
                    r = creq.get(
                        ts_url,
                        impersonate="chrome",
                        timeout=20,
                        headers=headers,
                        **proxy_kwargs(),
                    )
                    if r.status_code == 200:
                        tmp = ts_cache.with_suffix(".ts.tmp")
                        tmp.write_bytes(r.content)
                        os.replace(tmp, ts_cache)
                else:
                    req = urllib.request.Request(ts_url, headers=headers)
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        data = resp.read()
                    tmp = ts_cache.with_suffix(".ts.tmp")
                    tmp.write_bytes(data)
                    os.replace(tmp, ts_cache)
            except Exception:
                pass
            finally:
                _release_ts_lock(ts_key)
    except Exception:
        pass


def fetch_jable_hlsurl(code):
    creq = _get_creq()
    if not creq:
        return ""
    try:
        r = creq.get(
            f"https://jable.tv/videos/{code}/",
            impersonate="chrome",
            timeout=20,
            **proxy_kwargs(),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Referer": "https://jable.tv/",
            },
        )
        m = re.search(
            r'hlsUrl["\']?\s*[:=]\s*["\'](https?://[^"\']+\.m3u8[^"\']*)', r.text
        )
        return m.group(1) if m else ""
    except Exception:
        return ""


def resolve_hls_url(code):
    browser_map = read_browser_hls_map()
    url = (browser_map.get(code) or "").strip()
    if url:
        return url, "browser_map"
    cached_meta = PLAY_CACHE_DIR / code / "meta.json"
    if cached_meta.is_file():
        try:
            meta_raw = cached_meta.read_text(encoding="utf-8").strip()
            if meta_raw.startswith("http"):
                return meta_raw, "cache_meta"
            meta = json.loads(meta_raw)
            if meta.get("hls_url"):
                return meta["hls_url"], "cache_meta_json"
        except Exception:
            pass
    url = fetch_jable_hlsurl(code)
    if url:
        return url, "fetched"
    return "", "failed"


def proxy_playlist(code):
    cache_root = PLAY_CACHE_DIR / code
    m3u8_path = cache_root / "playlist.m3u8"
    meta_path = cache_root / "meta.json"
    if m3u8_path.is_file() and (time.time() - m3u8_path.stat().st_mtime) < CACHE_OK_TTL:
        inc_play()
        return m3u8_path.read_bytes(), "cache"
    hls_url, source = resolve_hls_url(code)
    if not hls_url:
        inc_play_fail()
        return None, "404"
    try:
        req = urllib.request.Request(
            hls_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://jable.tv/",
                "Origin": "https://jable.tv",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        cache_root.mkdir(parents=True, exist_ok=True)
        m3u8_path.write_bytes(data)
        meta_path.write_text(hls_url, encoding="utf-8")
        inc_play()
        threading.Thread(
            target=_prefetch_ts,
            args=(code, m3u8_path, meta_path, hls_url),
            daemon=True,
        ).start()
        evict_play_cache()
        return data, source
    except Exception:
        inc_play_fail()
        return None, "fetch_error"


def request_play(code):
    """异步播放请求：如果缓存命中直接返回，否则启动后台解析并返回 pending 状态"""
    cache_root = PLAY_CACHE_DIR / code
    m3u8_path = cache_root / "playlist.m3u8"
    if m3u8_path.is_file() and (time.time() - m3u8_path.stat().st_mtime) < CACHE_OK_TTL:
        inc_play()
        return {"status": PlayStatus.READY, "source": "cache"}
    if not _acquire_resolve_lock(code):
        return {"status": _get_resolve_status(code)["status"], "source": "already_resolving"}
    threading.Thread(target=_async_resolve, args=(code,), daemon=True).start()
    return {"status": PlayStatus.PENDING, "source": "started"}


def get_play_status(code):
    status = _get_resolve_status(code)
    m3u8_path = PLAY_CACHE_DIR / code / "playlist.m3u8"
    if m3u8_path.is_file() and (time.time() - m3u8_path.stat().st_mtime) < CACHE_OK_TTL:
        return {"status": PlayStatus.READY, "source": "cache", "error": ""}
    return {"status": status["status"], "source": "resolve", "error": status.get("error", "")}


def proxy_ts_segment(code, name):
    cache_root = PLAY_CACHE_DIR / code
    ts_path = cache_root / name
    if ts_path.is_file() and (time.time() - ts_path.stat().st_mtime) < CACHE_OK_TTL:
        return ts_path.read_bytes(), "cache"
    meta_path = cache_root / "meta.json"
    hls_url = ""
    if meta_path.is_file():
        try:
            meta_raw = meta_path.read_text(encoding="utf-8").strip()
            if meta_raw.startswith("http"):
                hls_url = meta_raw
            else:
                meta = json.loads(meta_raw)
                hls_url = meta.get("hls_url", "")
        except Exception:
            pass
    if not hls_url:
        return None, "no_meta"
    base_url = hls_url.rsplit("/", 1)[0]
    ts_url = base_url + "/" + name
    ts_key = f"{code}:{name}"
    if not _acquire_ts_lock(ts_key):
        _wait_ts_lock(ts_key)
        if ts_path.is_file():
            return ts_path.read_bytes(), "cache_after_wait"
        return None, "wait_failed"
    try:
        if ts_path.is_file():
            return ts_path.read_bytes(), "cache"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://jable.tv/",
        }
        creq = _get_creq()
        if creq:
            r = creq.get(
                ts_url,
                impersonate="chrome",
                timeout=20,
                headers=headers,
                **proxy_kwargs(),
            )
            if r.status_code == 200:
                data = r.content
            else:
                return None, f"status_{r.status_code}"
        else:
            req = urllib.request.Request(ts_url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
        tmp = ts_path.with_suffix(".ts.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, ts_path)
        return data, "fetched"
    except Exception:
        return None, "fetch_error"
    finally:
        _release_ts_lock(ts_key)


def rewrite_m3u8_ts_paths(m3u8_text, code):
    lines = m3u8_text.split("\n")
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped.endswith(".ts"):
            out.append(f"/play/{code}/{stripped}")
        else:
            out.append(line)
    return "\n".join(out)
