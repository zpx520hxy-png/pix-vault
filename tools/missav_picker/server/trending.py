import re
import json
import os
import time
import hashlib
import threading
from pathlib import Path

from .config import ROOT, TREND_CACHE_DIR, TREND_OK_TTL, TREND_FAIL_TTL, proxy_kwargs
from .cache import get_cache_size

TREND_LOCKS = {
    source: {period: threading.Lock() for period in ("daily", "weekly")}
    for source in ("missav", "jable")
}
TREND_PROGRESS_LOCK = threading.Lock()
TREND_PROGRESS = {
    source: {
        period: {
            "active": False,
            "attempted": 0,
            "total": 0,
            "items": 0,
            "stage": "idle",
        }
        for period in ("daily", "weekly")
    }
    for source in ("missav", "jable")
}
JABLE_METADATA_PATH = ROOT / ".jable_trending_metadata.json"
MISSAV_METADATA_PATH = ROOT / ".missav_trending_metadata.json"

TREND_REMOTE_URLS = {
    "missav": {
        "daily": [
            ("https://missav.ai/dm301/cn/today-hot", "period"),
            ("https://missav.ai/cn/today-hot", "period"),
            ("https://missav.ai/cn", "homepage"),
            ("https://missav.ai/dm285/ja", "homepage"),
        ],
        "weekly": [
            ("https://missav.ai/dm170/cn/weekly-hot", "period"),
            ("https://missav.ai/cn/weekly-hot", "period"),
            ("https://missav.ai/cn", "homepage"),
        ],
    },
    "jable": {
        "daily": [
            (
                "https://jable.tv/hot/?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed_today",
                "period",
            ),
            ("https://jable.tv/videos/?sort=popular", "period"),
            ("https://jable.tv/", "homepage"),
        ],
        "weekly": [
            (
                "https://jable.tv/hot/?mode=async&function=get_block&block_id=list_videos_common_videos_list&sort_by=video_viewed_week",
                "period",
            ),
            ("https://jable.tv/videos/?mode=weekly", "period"),
            ("https://jable.tv/", "homepage"),
        ],
    },
}


def _trend_path(source, period):
    return TREND_CACHE_DIR / f"{source}_{period}.json"


def _remote_trend_path(source, period):
    return TREND_CACHE_DIR / f"{source}_{period}_remote.json"


def _read_cached_trend(path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_trend_cache(source, period, data):
    path = _trend_path(source, period)
    payload = dict(data)
    payload["_ts"] = time.time()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def import_manual_jable_trending(period, raw_text):
    if period not in ("daily", "weekly"):
        raise ValueError("invalid period")
    text = str(raw_text or "")
    codes = []
    seen = set()
    patterns = (
        r"https?://(?:www\.)?jable\.tv/videos/([a-z0-9-]+)/?",
        r"(?:^|[^a-z0-9])([a-z]{2,12}-\d{2,8})(?=$|[^a-z0-9])",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            code = match.group(1).lower().strip()
            if not code or code in seen:
                continue
            seen.add(code)
            codes.append(code)
            if len(codes) >= 20:
                break
        if len(codes) >= 20:
            break
    if not codes:
        raise ValueError("no jable video links or codes found")
    items = _hydrate_trending_items(
        "jable",
        [{"code": code, "url": f"https://jable.tv/videos/{code}/"} for code in codes],
    )
    now = int(time.time() * 1000)
    data = {
        "source": "jable",
        "period": period,
        "items": items,
        "fetchedAt": now,
        "manualImportedAt": now,
        "sourceMode": "manual",
        "sourceUrl": "manual-import",
        "remote": False,
        "tried": [],
        "upstreamStatus": "",
        "retryAfterSeconds": 0,
    }
    _write_trend_cache("jable", period, data)
    data["cacheHit"] = False
    data["cacheAgeSeconds"] = 0
    return data


def _cache_ttl(data):
    if data.get("error") or data.get("retryAfterSeconds"):
        return TREND_FAIL_TTL
    return TREND_OK_TTL


def _cached_response(data, age):
    data = dict(data)
    data.pop("_ts", None)
    source = str(data.get("source") or "")
    if source in ("missav", "jable"):
        data["items"] = _hydrate_trending_items(source, data.get("items") or [])
    data["cacheHit"] = True
    data["cacheAgeSeconds"] = int(age)
    return data


def _last_remote_trend(source, period):
    cached = _read_cached_trend(_remote_trend_path(source, period))
    if not cached or not cached.get("items"):
        return None
    cached.pop("_ts", None)
    cached["sourceMode"] = "stale_remote"
    cached["remote"] = False
    cached["staleFetchedAt"] = cached.get("fetchedAt")
    cached["fetchedAt"] = int(time.time() * 1000)
    cached["upstreamStatus"] = "challenge"
    cached["retryAfterSeconds"] = TREND_FAIL_TTL
    return cached


def _trend_http_get(url, referer, fresh=False):
    timeout = 8 if fresh else 12
    diagnostic = {"status": 0, "bytes": 0, "error": ""}
    try:
        from curl_cffi import requests as creq

        r = creq.get(
            url,
            impersonate="chrome124",
            timeout=timeout,
            **proxy_kwargs(),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Referer": referer,
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )
        diagnostic["status"] = r.status_code
        diagnostic["bytes"] = len(r.content or b"")
        if r.status_code == 200 and r.text:
            return r.text, diagnostic
        diagnostic["error"] = (
            "challenge" if "just a moment" in r.text.lower() else "http"
        )
        return "", diagnostic
    except Exception as e:
        diagnostic["error"] = type(e).__name__
    import urllib.request

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Referer": referer,
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )
        proxy = proxy_kwargs().get("proxy")
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(
                {"http": proxy, "https": proxy} if proxy else {}
            )
        )
        with opener.open(req, timeout=timeout) as resp:
            data = resp.read()
            diagnostic["status"] = getattr(resp, "status", 200)
            diagnostic["bytes"] = len(data)
        if data:
            return data.decode("utf-8", errors="ignore"), diagnostic
    except Exception as e:
        diagnostic["error"] = diagnostic["error"] or type(e).__name__
    return "", diagnostic


def _trend_referer(source):
    return "https://jable.tv/" if source == "jable" else "https://missav.ai/"


def _remote_url_candidates(source, period):
    by_source = TREND_REMOTE_URLS.get(source) or TREND_REMOTE_URLS["missav"]
    return by_source.get(period) or by_source["daily"]


def _set_trend_progress(source, period, **values):
    with TREND_PROGRESS_LOCK:
        TREND_PROGRESS[source][period].update(values)


def get_trending_progress(source, period):
    with TREND_PROGRESS_LOCK:
        return dict(TREND_PROGRESS[source][period])


_MISSAV_CODE_RE = re.compile(
    r"/(?:((?:dm\d+))/)?(?:cn|ja|en|ko)/([A-Z]{2,8}-\d{2,8}(?:-[A-Z0-9]{2,8})?)(?![A-Za-z0-9-])",
    re.I,
)
_MISSAV_COVER_RE = re.compile(
    r"https?://[a-z0-9.-]*fourhoi\.com/[^\"' )]+cover[^\"' )]*", re.I
)


def _is_placeholder_cover(url):
    return "assets/images/placeholder" in (url or "").lower()


def _has_chinese_title(text):
    text = text or ""
    return bool(re.search(r"[\u4e00-\u9fff]", text)) and not bool(
        re.search(r"[\u3040-\u30ff]", text)
    )


def _find_jable_cover(html):
    matches = re.findall(
        r"(?:data-original|data-src|src)=[\"'](https?://assets-cdn\.jable\.tv/[^\"' ]+\.(?:jpe?g|png|webp))",
        html,
        re.I,
    )
    return next((url for url in matches if not _is_placeholder_cover(url)), "")


def _parse_missav_trending(html, period):
    if not html:
        return []
    snippet = html
    m = re.search(
        r"<section[^>]*id=[\"\'](?:popular|trending|hot|weekly|hot-weekly|popular-week|popular-month)[\"\'].*?</section>",
        html,
        re.I | re.S,
    )
    if m:
        snippet = m.group(0)
    if not _MISSAV_CODE_RE.search(snippet):
        idx = html.lower().find("<footer")
        if idx > 0:
            snippet = html[:idx]
    items = []
    seen = set()
    for m in _MISSAV_CODE_RE.finditer(snippet):
        dm = m.group(1) or ""
        code = m.group(2).lower()
        if code in seen or code.endswith("cover-t.jpg"):
            continue
        seen.add(code)
        start = m.start()
        end = min(len(snippet), m.end() + 2200)
        local = snippet[start:end]
        cover_m = _MISSAV_COVER_RE.search(local)
        cover = cover_m.group(0) if cover_m else ""
        title = ""
        for tm in re.finditer(r"(?:alt|title)=[\"']([^\"']{1,200})[\"']", local):
            t = tm.group(1).strip()
            if t and t.lower() != code and "cover" not in t.lower():
                title = t
                break
        items.append(
            {
                "code": code,
                "title": title,
                "cover": cover,
                "url": f"https://missav.ai/{dm + '/' if dm else ''}cn/{code}",
            }
        )
        if len(items) >= 20:
            break
    return items


def _parse_jable_trending(html):
    if not html:
        return []
    items = []
    seen = set()
    for m in re.finditer(
        r"href=[\"\'](?:https?://jable\.tv)?/videos/([a-z0-9-]+)/?[\"\']", html, re.I
    ):
        code = m.group(1).lower()
        if code in seen:
            continue
        seen.add(code)
        end_anchor = html.find("</a>", m.end())
        if end_anchor == -1 or end_anchor - m.start() > 1200:
            end_anchor = m.end() + 220
        local = html[m.start() : min(len(html), end_anchor + 4)]
        cover = _find_jable_cover(local)
        if not cover:
            start = max(0, m.start() - 260)
            local = html[start : min(len(html), m.end() + 220)]
        if not cover:
            cover = _find_jable_cover(local)
        title_m = re.search(r"(?:alt|title|h4|h3)[^>]*>([^<]{2,200})<", local, re.I)
        title = title_m.group(1).strip() if title_m else ""
        items.append(
            {
                "code": code,
                "title": title,
                "cover": cover,
                "url": f"https://jable.tv/videos/{code}/",
            }
        )
        if len(items) >= 20:
            break
    return items


def _local_fallback_trending(source, period):
    data_file = ROOT / ("jable_data.json" if source == "jable" else "picker_data.json")
    if not data_file.is_file():
        return []
    try:
        data = json.loads(data_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    videos = data.get("videos") or []
    import datetime as _dt

    today = _dt.date.today()
    window_days = 90 if period == "daily" else 365

    def parse_date(v):
        d = v.get("date") or ""
        try:
            return _dt.date.fromisoformat(d)
        except Exception:
            return None

    def synthetic_date(v):
        if period == "daily":
            return today - _dt.timedelta(days=7)
        else:
            return today - _dt.timedelta(days=90)

    with_date = []
    for v in videos:
        d = parse_date(v)
        if d is None:
            d = synthetic_date(v)
        with_date.append((v, d))
    with_date.sort(key=lambda x: x[1], reverse=True)

    def hot_score(v, d):
        delta = (today - d).days
        if delta <= 0:
            return 1000
        if delta <= window_days:
            return 1000 - delta
        return max(0, 100 - (delta - window_days) * 0.1)

    salt = "d" if period == "daily" else "w"
    if period == "daily":
        seed = int(today.strftime("%Y%m%d%H"))
    else:
        seed = int(today.strftime("%Y%m%d"))

    def score(v, d):
        h = hashlib.md5(f"{salt}|{seed}|{v.get('code') or ''}".encode()).hexdigest()
        return hot_score(v, d) + int(h[:6], 16) / 0xFFFFFF

    ranked = sorted(with_date, key=lambda x: score(x[0], x[1]), reverse=True)
    if len(ranked) < 20:
        no_date = [v for v in videos if parse_date(v) is None]

        def shuffle_key(v):
            h = hashlib.md5(f"{salt}|{seed}|{v.get('code') or ''}".encode()).hexdigest()
            return int(h[:8], 16)

        ranked = ranked + sorted(no_date, key=shuffle_key, reverse=True)
    out, seen = [], set()
    for v, d in ranked:
        c = (v.get("code") or "").lower()
        if not c or c in seen:
            continue
        seen.add(c)
        out.append(
            {
                "code": c,
                "title": v.get("title") or "",
                "cover": v.get("cover") or "",
                "url": v.get("url")
                or f"https://{'jable.tv' if source == 'jable' else 'missav.ws'}/",
                "date": d.isoformat() if d else "",
            }
        )
        if len(out) >= 20:
            break
    return out


def _local_video_map(source):
    data_file = ROOT / ("jable_data.json" if source == "jable" else "picker_data.json")
    if not data_file.is_file():
        return {}
    try:
        videos = json.loads(data_file.read_text(encoding="utf-8")).get("videos") or []
    except Exception:
        return {}
    return {(v.get("code") or "").lower(): v for v in videos if v.get("code")}


def trending_metadata_path(source):
    return JABLE_METADATA_PATH if source == "jable" else MISSAV_METADATA_PATH


def _trending_metadata_map(source):
    path = trending_metadata_path(source)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {
        str(code).lower(): value
        for code, value in data.items()
        if isinstance(value, dict)
    }


def _removed_video_keys():
    path = ROOT / ".removed_videos.json"
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {str(k).lower() for k in data.keys()}


def _hydrate_trending_items(source, items):
    local = _local_video_map(source)
    metadata = _trending_metadata_map(source)
    removed = _removed_video_keys()
    out = []
    seen = set()
    for it in items or []:
        code = (it.get("code") or "").lower()
        if not code or code in seen or f"{source}:{code}" in removed:
            continue
        local_v = local.get(code) or {}
        metadata_v = metadata.get(code) or {}
        seen.add(code)
        url = local_v.get("url") or it.get("url") or ""
        if not url:
            url = (
                f"https://jable.tv/videos/{code}/"
                if source == "jable"
                else f"https://missav.ai/cn/{code}"
            )
        remote_cover = it.get("cover") or ""
        local_cover = local_v.get("cover") or ""
        if _is_placeholder_cover(remote_cover):
            remote_cover = ""
        if _is_placeholder_cover(local_cover):
            local_cover = ""
        remote_title = (it.get("title") or "").strip()
        local_title = (local_v.get("title") or "").strip()
        metadata_title = (metadata_v.get("title") or "").strip()
        title = (
            local_title
            if _has_chinese_title(local_title)
            else metadata_title
            if _has_chinese_title(metadata_title)
            else remote_title
            if _has_chinese_title(remote_title)
            else "暂无中文简介"
        )
        out.append(
            {
                "code": local_v.get("code") or it.get("code") or code,
                "title": title,
                "cover": remote_cover or local_cover,
                "url": url,
                "date": local_v.get("date") or it.get("date") or "",
                "local": bool(local_v),
                "original_title": metadata_v.get("original_title")
                or local_v.get("original_title")
                or "",
                "actresses": metadata_v.get("actresses")
                or local_v.get("actresses")
                or [],
                "tags": metadata_v.get("tags") or local_v.get("tags") or [],
                "is_multi": bool(metadata_v.get("is_multi") or local_v.get("is_multi")),
            }
        )
        if len(out) >= 20:
            break
    return out


def _fill_trending_items(items, fallback, limit=20):
    result = []
    seen = set()
    for item in list(items or []) + list(fallback or []):
        code = (item.get("code") or "").lower()
        if not code or code in seen:
            continue
        seen.add(code)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _scrape_trending(source, period, fresh=False):
    tried = []
    source_url = ""
    source_mode = "remote"
    candidates = _remote_url_candidates(source, period)
    _set_trend_progress(
        source,
        period,
        active=True,
        attempted=0,
        total=len(candidates),
        items=0,
        stage="准备抓取",
    )
    if source == "missav":
        items = []
        homepage_items = []
        homepage_url = ""
        for index, (url, kind) in enumerate(candidates, 1):
            _set_trend_progress(source, period, attempted=index, stage="抓取榜单")
            parsed = []
            for attempt in range(1):
                html, diagnostic = _trend_http_get(
                    url, referer=_trend_referer(source), fresh=fresh
                )
                parsed = _parse_missav_trending(html, period)
                if parsed:
                    break
            _set_trend_progress(source, period, items=len(parsed), stage="解析榜单")
            tried.append({"url": url, "kind": kind, "items": len(parsed), **diagnostic})
            if parsed and kind == "period":
                items = parsed
                source_url = url
                source_mode = kind
                break
            if parsed and not homepage_items:
                homepage_items = parsed
                homepage_url = url
        if not items:
            if homepage_items:
                items = homepage_items
                source_url = homepage_url
                source_mode = "homepage"
            else:
                items = _local_fallback_trending(source, period)
                source_mode = "fallback"
        if len(items) < 20:
            items = _fill_trending_items(
                items,
                _local_fallback_trending(source, period),
            )
    else:
        data_file = ROOT / "jable_data.json"
        local_codes = set()
        if data_file.is_file():
            try:
                local_codes = {
                    v.get("code", "").lower()
                    for v in json.loads(data_file.read_text(encoding="utf-8")).get(
                        "videos", []
                    )
                }
            except Exception:
                pass
        items = []
        for index, (url, kind) in enumerate(candidates, 1):
            _set_trend_progress(source, period, attempted=index, stage="抓取榜单")
            remote_items = []
            for attempt in range(1):
                html, diagnostic = _trend_http_get(
                    url, referer=_trend_referer(source), fresh=fresh
                )
                remote_items = _parse_jable_trending(html)
                if remote_items:
                    break
            filtered = [it for it in remote_items if it.get("code") in local_codes]
            usable = remote_items
            _set_trend_progress(source, period, items=len(usable), stage="解析榜单")
            tried.append(
                {
                    "url": url,
                    "kind": kind,
                    "items": len(usable),
                    "localItems": len(filtered),
                    "remoteItems": len(remote_items),
                    **diagnostic,
                }
            )
            if usable and kind == "period":
                items = usable
                source_url = url
                source_mode = kind
                break
        if len(items) < 20:
            _set_trend_progress(source, period, stage="本地补位")
            local_items = _local_fallback_trending(source, period)
            seen = {it["code"] for it in items}
            for it in local_items:
                if it["code"] in seen:
                    continue
                items.append(it)
                seen.add(it["code"])
                if len(items) >= 20:
                    break
            if not source_url and items:
                source_mode = "fallback"
    items = _hydrate_trending_items(source, items)
    challenge_only = bool(tried) and all(
        item.get("error") == "challenge" for item in tried
    )
    return {
        "source": source,
        "period": period,
        "items": items,
        "fetchedAt": int(time.time() * 1000),
        "sourceMode": source_mode,
        "sourceUrl": source_url,
        "remote": source_mode != "fallback",
        "tried": tried[:5],
        "upstreamStatus": "challenge" if challenge_only else "",
        "retryAfterSeconds": TREND_FAIL_TTL if challenge_only else 0,
    }


def get_trending(source, period, force=False):
    path = _trend_path(source, period)
    manual_cached = None
    if path.is_file():
        cached = _read_cached_trend(path)
        if cached:
            age = time.time() - (cached.get("_ts", 0) or 0)
            if source == "jable" and cached.get("sourceMode") == "manual":
                manual_cached = cached
            if manual_cached and not force:
                return _cached_response(cached, age)
            ttl = _cache_ttl(cached)
            if not force and age < ttl:
                return _cached_response(cached, age)
    with TREND_LOCKS[source][period]:
        if path.is_file() and not force:
            cached = _read_cached_trend(path)
            if cached:
                age = time.time() - (cached.get("_ts", 0) or 0)
                ttl = _cache_ttl(cached)
                if age < ttl:
                    return _cached_response(cached, age)
        try:
            data = _scrape_trending(source, period, fresh=force)
        except Exception as e:
            data = {
                "source": source,
                "period": period,
                "items": [],
                "error": repr(e)[:120],
                "sourceMode": "error",
                "remote": False,
            }
        if not data.get("remote"):
            stale_remote = _last_remote_trend(source, period)
            if stale_remote:
                stale_remote["items"] = _fill_trending_items(
                    stale_remote.get("items"),
                    data.get("items"),
                )
                stale_remote["tried"] = data.get("tried") or []
                stale_remote["refreshFallback"] = True
                data = stale_remote
        if manual_cached and source == "jable" and not data.get("remote"):
            age = time.time() - (manual_cached.get("_ts", 0) or 0)
            response = _cached_response(manual_cached, age)
            response["refreshFallback"] = True
            return response
        _set_trend_progress(
            source,
            period,
            active=False,
            items=len(data.get("items") or []),
            stage="完成",
        )
        data["_ts"] = time.time()
        try:
            _write_trend_cache(source, period, data)
            if data.get("remote") and data.get("items"):
                remote_path = _remote_trend_path(source, period)
                remote_tmp = remote_path.with_suffix(".json.tmp")
                remote_tmp.write_text(
                    json.dumps(data, ensure_ascii=False), encoding="utf-8"
                )
                os.replace(remote_tmp, remote_path)
        except Exception:
            pass
        data.pop("_ts", None)
        data["cacheHit"] = False
        data["cacheAgeSeconds"] = 0
        return data
