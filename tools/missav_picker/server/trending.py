import re
import json
import time
import hashlib
import threading
from pathlib import Path

from .config import ROOT, TREND_CACHE_DIR, TREND_OK_TTL, TREND_FAIL_TTL, proxy_kwargs
from .cache import get_cache_size

TREND_LOCK = threading.Lock()


def _trend_path(source, period):
    return TREND_CACHE_DIR / f"{source}_{period}.json"


def _trend_http_get(url, referer):
    try:
        from curl_cffi import requests as creq

        r = creq.get(
            url,
            impersonate="chrome",
            timeout=15,
            **proxy_kwargs(),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Referer": referer,
            },
        )
        if r.status_code == 200 and r.text:
            return r.text
    except Exception:
        pass
    import urllib.request

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Referer": referer,
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if data:
            return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""
    return ""


_MISSAV_CODE_RE = re.compile(
    r"/(dm\d+)/cn/([A-Z0-9]{2,8}(?:-[A-Z0-9]{2,8})?)(?![A-Za-z0-9-])", re.I
)
_MISSAV_COVER_RE = re.compile(
    r"https?://[a-z0-9.-]*fourhoi\.com/[^\"' )]+cover[^\"' )]*", re.I
)


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
    else:
        idx = html.lower().find("<footer")
        if idx > 0:
            snippet = html[:idx]
    items = []
    seen = set()
    for m in _MISSAV_CODE_RE.finditer(snippet):
        dm = m.group(1)
        code = m.group(2).lower()
        if code in seen or code.endswith("cover-t.jpg"):
            continue
        seen.add(code)
        start = max(0, m.start() - 400)
        end = min(len(snippet), m.end() + 400)
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
                "url": f"https://missav.ws/{dm}/cn/{code}",
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
        cover_m = re.search(
            r"(?:data-original|data-src|src)=[\"\'](https?://assets-cdn\.jable\.tv/[^\"\' ]+\.(?:jpe?g|png|webp))",
            local,
            re.I,
        )
        if not cover_m:
            start = max(0, m.start() - 260)
            local = html[start : min(len(html), m.end() + 220)]
            cover_m = re.search(
                r"(?:data-original|data-src|src)=[\"\'](https?://assets-cdn\.jable\.tv/[^\"\' ]+\.(?:jpe?g|png|webp))",
                local,
                re.I,
            )
        title_m = re.search(r"(?:alt|title|h4|h3)[^>]*>([^<]{2,200})<", local, re.I)
        cover = cover_m.group(1) if cover_m else ""
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
    removed = _removed_video_keys()
    out = []
    seen = set()
    for it in items or []:
        code = (it.get("code") or "").lower()
        if not code or code in seen or f"{source}:{code}" in removed:
            continue
        local_v = local.get(code) or {}
        seen.add(code)
        url = local_v.get("url") or it.get("url") or ""
        if not url:
            url = (
                f"https://jable.tv/videos/{code}/"
                if source == "jable"
                else f"https://missav.ws/cn/{code}"
            )
        out.append(
            {
                "code": local_v.get("code") or it.get("code") or code,
                "title": it.get("title") or local_v.get("title") or "",
                "cover": it.get("cover") or local_v.get("cover") or "",
                "url": url,
                "date": local_v.get("date") or it.get("date") or "",
                "local": bool(local_v),
            }
        )
        if len(out) >= 20:
            break
    return out


def _scrape_trending(source, period):
    if source == "missav":
        url = "https://missav.ws/"
        html = _trend_http_get(url, referer="https://missav.ws/")
        items = _parse_missav_trending(html, period)
        if not items:
            items = _local_fallback_trending(source, period)
    else:
        url = "https://jable.tv/"
        html = _trend_http_get(url, referer="https://jable.tv/")
        remote_items = _parse_jable_trending(html)
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
        items = [it for it in remote_items if it.get("code") in local_codes]
        if len(items) < 20:
            local_items = _local_fallback_trending(source, period)
            seen = {it["code"] for it in items}
            for it in local_items:
                if it["code"] in seen:
                    continue
                items.append(it)
                seen.add(it["code"])
                if len(items) >= 20:
                    break
    items = _hydrate_trending_items(source, items)
    return {
        "source": source,
        "period": period,
        "items": items,
        "fetchedAt": int(time.time() * 1000),
    }


def get_trending(source, period):
    path = _trend_path(source, period)
    if path.is_file():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            age = time.time() - (cached.get("_ts", 0) or 0)
            ttl = TREND_FAIL_TTL if cached.get("error") else TREND_OK_TTL
            if age < ttl and cached.get("items"):
                cached.pop("_ts", None)
                return cached
        except Exception:
            pass
    with TREND_LOCK:
        if path.is_file():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                age = time.time() - (cached.get("_ts", 0) or 0)
                ttl = TREND_FAIL_TTL if cached.get("error") else TREND_OK_TTL
                if age < ttl and cached.get("items"):
                    cached.pop("_ts", None)
                    return cached
            except Exception:
                pass
        try:
            data = _scrape_trending(source, period)
        except Exception as e:
            data = {
                "source": source,
                "period": period,
                "items": [],
                "error": repr(e)[:120],
            }
        data["_ts"] = time.time()
        try:
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except Exception:
            pass
        data.pop("_ts", None)
        return data
