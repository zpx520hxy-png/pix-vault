import re
import json
import time
import os
import threading
import urllib.request
import urllib.error
from pathlib import Path
from enum import Enum

from .config import (
    ROOT,
    CACHE_DIR,
    PLAY_CACHE_DIR,
    TEMP_PLAY_CACHE_DIR,
    CACHE_OK_TTL,
    proxy_kwargs,
)
from .cache import (
    read_browser_hls_map,
    upsert_browser_hls,
    inc_play,
    inc_play_fail,
    evict_play_cache,
    evict_temp_play_cache,
)


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
    return _RESOLVE_STATUS.get(
        code, {"status": PlayStatus.PENDING, "error": "", "ts": 0}
    )


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


def _cache_root(code, persistent):
    return (PLAY_CACHE_DIR if persistent else TEMP_PLAY_CACHE_DIR) / code


def _async_resolve(code, persistent=False):
    _set_resolve_status(code, PlayStatus.PENDING)
    try:
        hls_url, source = resolve_hls_url(code)
        if not hls_url:
            _set_resolve_status(code, PlayStatus.NOT_FOUND, "hlsUrl not found")
            return
        data = _http_get_bytes(
            hls_url,
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://jable.tv/",
                "Origin": "https://jable.tv",
            },
            timeout=15,
        )
        cache_root = _cache_root(code, persistent)
        cache_root.mkdir(parents=True, exist_ok=True)
        m3u8_path = cache_root / "playlist.m3u8"
        meta_path = cache_root / "meta.json"
        m3u8_path.write_bytes(data)
        meta_path.write_text(hls_url, encoding="utf-8")
        _set_resolve_status(code, PlayStatus.READY)
        if persistent:
            threading.Thread(
                target=_prefetch_ts,
                args=(code, m3u8_path, meta_path, hls_url),
                daemon=True,
            ).start()
    except Exception as e:
        _set_resolve_status(code, PlayStatus.FAILED, repr(e)[:120])
    finally:
        _release_resolve_lock(code)


_TS_DL_LOCKS = {}
_TS_DL_MASTER = {}
_TS_DL_LOCK = threading.Lock()
_PREFETCHED = set()
_PREFETCH_LOCK = threading.Lock()
_ACTIVE_PLAYBACK = {}
_ACTIVE_PLAYBACK_LOCK = threading.Lock()
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


def _http_get_bytes(url, headers, timeout=15):
    creq = _get_creq()
    if creq:
        r = creq.get(
            url,
            impersonate="chrome124",
            timeout=timeout,
            headers=headers,
            **proxy_kwargs(),
        )
        if r.status_code != 200:
            raise urllib.error.HTTPError(url, r.status_code, "HTTP error", {}, None)
        return r.content
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _fetch_playlist_with_refresh(code, hls_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://jable.tv/",
        "Origin": "https://jable.tv",
    }
    try:
        return _http_get_bytes(hls_url, headers, timeout=15), hls_url
    except Exception:
        for attempt in range(3):
            fresh_url = fetch_jable_hlsurl(code)
            if fresh_url and fresh_url != hls_url:
                try:
                    data = _http_get_bytes(fresh_url, headers, timeout=15)
                    upsert_browser_hls(code, fresh_url)
                    return data, fresh_url
                except Exception:
                    pass
            if attempt < 2:
                time.sleep(0.5)
        raise


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


def _mark_active_playback(code):
    with _ACTIVE_PLAYBACK_LOCK:
        _ACTIVE_PLAYBACK[code] = time.monotonic()


def _is_active_playback(code, max_age=90):
    with _ACTIVE_PLAYBACK_LOCK:
        started = _ACTIVE_PLAYBACK.get(code)
        if not started:
            return False
        if time.monotonic() - started > max_age:
            _ACTIVE_PLAYBACK.pop(code, None)
            return False
        return True


def _prefetch_ts(code, m3u8_path, meta_path, hls_url, initial_delay=15):
    key = f"{code}:prefetch"
    with _PREFETCH_LOCK:
        if key in _PREFETCHED:
            return
        _PREFETCHED.add(key)
    if initial_delay > 0:
        time.sleep(initial_delay)
    try:
        meta = meta_path.read_text(encoding="utf-8").strip()
        hls_url = meta if meta.startswith("http") else hls_url
        if not hls_url:
            return
        base_url = hls_url.rsplit("/", 1)[0]
        m3u8_text = m3u8_path.read_text(encoding="utf-8")
        ts_names = re.findall(r"^([^#].+\.ts)$", m3u8_text, re.M)
        key_match = re.search(r'#EXT-X-KEY:.*URI="([^"]+)"', m3u8_text)
        key_name = key_match.group(1) if key_match else None
        if not ts_names:
            return
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://jable.tv/",
        }
        creq = _get_creq()
        names_to_fetch = []
        if key_name:
            names_to_fetch.append(key_name)
        # 预取只作为收藏离线缓冲的低优先级任务。正在播放时立即暂停，
        # 让浏览器请求的当前分片独占上游连接，避免缓冲被后台下载拖慢。
        names_to_fetch.extend(ts_names)
        for name in names_to_fetch:
            if _is_active_playback(code):
                return
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
                        impersonate="chrome124",
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
            impersonate="chrome124",
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


def is_play_cache_complete(code):
    cache_root = PLAY_CACHE_DIR / code
    m3u8_path = cache_root / "playlist.m3u8"
    if not m3u8_path.is_file():
        return False
    try:
        m3u8_text = m3u8_path.read_text(encoding="utf-8")
        ts_names = re.findall(r"^([^#].+\.ts)$", m3u8_text, re.M)
        key_match = re.search(r'#EXT-X-KEY:.*URI="([^"]+)"', m3u8_text)
        key_name = key_match.group(1) if key_match else None
        if not ts_names:
            return False
        if key_name and not (cache_root / key_name).is_file():
            return False
        return all((cache_root / name).is_file() for name in ts_names)
    except Exception:
        return False


def proxy_playlist(code, persistent=False):
    cache_root = _cache_root(code, persistent)
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
        data, hls_url = _fetch_playlist_with_refresh(code, hls_url)
        cache_root.mkdir(parents=True, exist_ok=True)
        m3u8_path.write_bytes(data)
        meta_path.write_text(hls_url, encoding="utf-8")
        inc_play()
        if persistent:
            threading.Thread(
                target=_prefetch_ts,
                args=(code, m3u8_path, meta_path, hls_url),
                daemon=True,
            ).start()
        return data, source
    except Exception:
        inc_play_fail()
        return None, "fetch_error"


def request_play(code, persistent=False):
    """异步播放请求：
    - 完整缓存命中 => ready
    - 只有 playlist / meta 但分片不完整 => 后台补齐,返回 pending
    - 完全没缓存 => 正常走解析
    """
    if not persistent:
        evict_temp_play_cache()
    cache_root = _cache_root(code, persistent)
    m3u8_path = cache_root / "playlist.m3u8"
    meta_path = cache_root / "meta.json"
    if m3u8_path.is_file() and (time.time() - m3u8_path.stat().st_mtime) < CACHE_OK_TTL:
        if meta_path.is_file():
            inc_play()
            return {"status": PlayStatus.READY, "source": "cache"}
        if is_play_cache_complete(code):
            inc_play()
            return {"status": PlayStatus.READY, "source": "cache_complete"}
        if not persistent:
            inc_play()
            return {"status": PlayStatus.READY, "source": "temp_cache"}
        # 已有播放链路但缓存不完整,后台继续补齐 key/ts
        if not _acquire_resolve_lock(code):
            return {
                "status": _get_resolve_status(code)["status"],
                "source": "already_resolving",
            }

        def _hydrate_existing():
            _set_resolve_status(code, PlayStatus.PENDING)
            try:
                meta = (
                    meta_path.read_text(encoding="utf-8").strip()
                    if meta_path.is_file()
                    else ""
                )
                hls_url = meta if meta.startswith("http") else ""
                if not hls_url:
                    _set_resolve_status(code, PlayStatus.NOT_FOUND, "meta missing")
                    return
                _prefetch_ts(code, m3u8_path, meta_path, hls_url, initial_delay=0)
                if is_play_cache_complete(code):
                    _set_resolve_status(code, PlayStatus.READY)
                else:
                    _set_resolve_status(code, PlayStatus.FAILED, "cache incomplete")
            except Exception as e:
                _set_resolve_status(code, PlayStatus.FAILED, repr(e)[:120])
            finally:
                _release_resolve_lock(code)

        threading.Thread(target=_hydrate_existing, daemon=True).start()
        return {"status": PlayStatus.PENDING, "source": "hydrate"}
    if not _acquire_resolve_lock(code):
        return {
            "status": _get_resolve_status(code)["status"],
            "source": "already_resolving",
        }
    threading.Thread(
        target=_async_resolve, args=(code, persistent), daemon=True
    ).start()
    return {"status": PlayStatus.PENDING, "source": "started"}


def get_play_status(code, persistent=False):
    status = _get_resolve_status(code)
    m3u8_path = _cache_root(code, persistent) / "playlist.m3u8"
    meta_path = _cache_root(code, persistent) / "meta.json"
    if m3u8_path.is_file() and (time.time() - m3u8_path.stat().st_mtime) < CACHE_OK_TTL:
        if meta_path.is_file():
            return {"status": PlayStatus.READY, "source": "cache", "error": ""}
        if is_play_cache_complete(code):
            return {"status": PlayStatus.READY, "source": "cache_complete", "error": ""}
        return {"status": PlayStatus.PENDING, "source": "hydrate", "error": ""}
    if status["status"] in (PlayStatus.FAILED, PlayStatus.NOT_FOUND):
        data, source = proxy_playlist(code, persistent=persistent)
        if data is not None:
            _set_resolve_status(code, PlayStatus.READY)
            return {"status": PlayStatus.READY, "source": source, "error": ""}
    return {
        "status": status["status"],
        "source": "resolve",
        "error": status.get("error", ""),
    }


def proxy_ts_segment(code, name, persistent=False):
    _mark_active_playback(code)
    cache_root = _cache_root(code, persistent)
    ts_path = cache_root / name
    if ts_path.is_file() and (time.time() - ts_path.stat().st_mtime) < CACHE_OK_TTL:
        return ts_path.read_bytes(), "cache"
    meta_path = cache_root / "meta.json"
    # Browser-captured URLs are newer than the playlist metadata written by a
    # prior playback. Prefer them so later seeks do not keep using expired HLS
    # signatures for uncached segments.
    hls_url = (read_browser_hls_map().get(code) or "").strip()
    if meta_path.is_file():
        try:
            meta_raw = meta_path.read_text(encoding="utf-8").strip()
            if not hls_url and meta_raw.startswith("http"):
                hls_url = meta_raw
            elif not hls_url:
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


def rewrite_m3u8_ts_paths(m3u8_text, code, persistent=False):
    lines = m3u8_text.split("\n")
    out = []
    persist = "?persist=favorite" if persistent else ""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped.endswith(".ts"):
            out.append(f"/play/{code}/{stripped}{persist}")
        elif stripped.startswith("#EXT-X-KEY:"):
            out.append(
                re.sub(
                    r'URI="([^"/]+)"',
                    lambda match: f'URI="/play/{code}/{match.group(1)}{persist}"',
                    line,
                )
            )
        else:
            out.append(line)
    return "\n".join(out)
