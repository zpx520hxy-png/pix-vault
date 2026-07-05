"""MissAV Picker 局域网服务器(含图片代理+磁盘缓存+gzip)"""

import http.server
import socket
import sys
import gzip
import io
import json
import os
import re
import time
import hashlib
import urllib.request
import urllib.error
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PORT = int(os.environ.get("MISSAV_PICKER_PORT", "8699"))
ROOT = Path(__file__).parent
CACHE_DIR = ROOT / ".img_cache"
SYNC_STATE_FILE = ROOT / ".shared_state.json"
CACHE_MAX_BYTES = 500 * 1024 * 1024  # 500MB 上限
CACHE_FAIL_TTL = 300  # 失败结果缓存 5 分钟,避免反复请求被墙域名
CACHE_OK_TTL = 7 * 24 * 3600  # 成功结果 7 天 HTTP 缓存

# 1x1 透明 PNG,被墙 / 404 时用作占位
PLACEHOLDER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63f8cf0000000300010054f073b70000000049454e44ae"
    "426082"
)

# 简易 LRU 计数器(原子近似)
_HIT = 0
_MISS = 0
_FAIL = 0
_PLAY = 0
_PLAY_FAIL = 0

# curl_cffi session 复用(减少 TLS 握手开销)
_CREQ_SESSION = None
_CREQ_LOCK = threading.Lock()


def _get_creq():
    """复用 curl_cffi Session,避免每个 ts 请求重新 TLS 握手。"""
    global _CREQ_SESSION
    with _CREQ_LOCK:
        if _CREQ_SESSION is None:
            from curl_cffi import requests as creq

            _CREQ_SESSION = creq.Session(impersonate="chrome")
        return _CREQ_SESSION


def _prefetch_ts(code: str, m3u8_path: Path, meta_path: Path, hls_url: str):
    """后台并发预热 ts 分片:延迟 15 秒等 hls.js 充分缓冲开头后,
    1 路低速预热第 21~80 片(不抢开头,不占满带宽)。"""
    time.sleep(15)  # 等 hls.js 开播并缓冲开头
    cache_root = m3u8_path.parent
    try:
        text = m3u8_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return
    segs = []
    for line in text.split("\n"):
        s = line.strip()
        if s and not s.startswith("#") and s.endswith(".ts"):
            name = s.rsplit("/", 1)[-1]
            segs.append(name)
    if len(segs) < 25:
        return
    # 跳过开头 20 片(hls.js 在下),预热第 21~80 片
    todo = []
    for name in segs[20:80]:
        if not (cache_root / name).is_file():
            todo.append(name)
    if not todo:
        return
    base_url = hls_url.rsplit("/", 1)[0]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Referer": "https://jable.tv/",
        "Origin": "https://jable.tv",
    }
    # 下载锁:标记正在下载的分片,避免和 hls.js 请求重复下载

    def _dl(name):
        ts_cache = cache_root / name
        if ts_cache.is_file():
            return
        if not _acquire_ts_lock(code + "/" + name):
            return  # 已有线程在下载
        try:
            if ts_cache.is_file():
                return
            ts_url = base_url + "/" + name
            from curl_cffi import requests as creq

            r = creq.get(
                ts_url,
                impersonate="chrome",
                proxy="http://127.0.0.1:7890",
                timeout=20,
                headers=headers,
            )
            if r.status_code == 200:
                tmp = ts_cache.with_suffix(".ts.tmp")
                tmp.write_bytes(r.content)
                os.replace(tmp, ts_cache)
        except Exception:
            pass
        finally:
            _release_ts_lock(code + "/" + name)

    # 1 路低速预热(不抢 hls.js 带宽)
    try:
        for name in todo:
            _dl(name)
    except Exception:
        pass


# 已预热的 code 集合(避免重复预热)
_PREFETCHED = set()
_PREFETCH_LOCK = threading.Lock()

# 全局 ts 下载锁:某分片正在下载时,其他请求等待而非重复下载
_TS_DL_LOCKS = {}
_TS_DL_MASTER = threading.Lock()


def _acquire_ts_lock(key: str):
    """获取某 ts 分片的下载锁,返回 True=需下载,False=已有线程在下(等待即可)。"""
    with _TS_DL_MASTER:
        if key in _TS_DL_LOCKS:
            return False  # 已有线程在下载
        _TS_DL_LOCKS[key] = threading.Event()
        return True


def _release_ts_lock(key: str):
    with _TS_DL_MASTER:
        ev = _TS_DL_LOCKS.pop(key, None)
    if ev:
        ev.set()  # 通知等待者


def _wait_ts_lock(key: str, timeout: float = 30):
    """等待某分片下载完成,返回 True=已下载完(可读缓存)。"""
    with _TS_DL_MASTER:
        ev = _TS_DL_LOCKS.get(key)
    if ev:
        return ev.wait(timeout)
    return False


# ---- 热门(每日/每周) ----
TREND_CACHE_DIR = CACHE_DIR / "trend"
TREND_CACHE_DIR.mkdir(parents=True, exist_ok=True)
TREND_OK_TTL = 30 * 60  # 成功 30 分钟
TREND_FAIL_TTL = 5 * 60  # 失败 5 分钟(避免反复打)
TREND_LOCK = threading.Lock()


def _trend_path(source: str, period: str) -> Path:
    return TREND_CACHE_DIR / f"{source}_{period}.json"


def _trend_http_get(url: str, referer: str) -> str:
    """按可用的方式拉取 HTML: 优先 curl_cffi 走 7890 代理,失败回退 urllib 直连"""
    try:
        from curl_cffi import requests as creq

        r = creq.get(
            url,
            impersonate="chrome",
            proxy="http://127.0.0.1:7890",
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Referer": referer,
            },
        )
        if r.status_code == 200 and r.text:
            return r.text
    except Exception:
        pass
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
_MISSAV_TITLE_RE = re.compile(r"<[^>]+title=[\"']([^\"']{1,200})[\"']", re.I)


def _parse_missav_trending(html: str, period: str) -> list:
    """从 missav.ws 热门页抽 code/title/cover,最多 20 部,按页面顺序"""
    if not html:
        return []
    # 截取"热门"区域:missav 首页/热门页里常用 id="popular" 或 class 含 popular/trending
    snippet = html
    m = re.search(
        r"<section[^>]*id=[\"\'](?:popular|trending|hot|weekly|hot-weekly|popular-week|popular-month)[\"\'].*?</section>",
        html,
        re.I | re.S,
    )
    if m:
        snippet = m.group(0)
    else:
        # 退化:在第一个 footer 之前截
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
        # 在 code 周围找最近的 title 和 cover
        start = max(0, m.start() - 400)
        end = min(len(snippet), m.end() + 400)
        local = snippet[start:end]
        cover_m = _MISSAV_COVER_RE.search(local)
        cover = cover_m.group(0) if cover_m else ""
        # title 优先从 alt / title 属性里找
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


def _parse_jable_trending(html: str) -> list:
    if not html:
        return []
    items = []
    seen = set()
    # jable 热门页:卡片 <a href="/videos/<code>/">
    for m in re.finditer(
        r"href=[\"\'](?:https?://jable\.tv)?/videos/([a-z0-9-]+)/?[\"\']", html, re.I
    ):
        code = m.group(1).lower()
        if code in seen:
            continue
        seen.add(code)
        start = max(0, m.start() - 600)
        end = min(len(html), m.end() + 200)
        local = html[start:end]
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


def _local_fallback_trending(source: str, period: str) -> list:
    """远端拉不到时,基于本地数据(JSON 库)给一个保底热门列表
    daily  -> 最近 90 天内发布的作品
    weekly -> 最近 365 天内发布的作品
    daily/weekly 命中区域不同(daily 范围更窄、更新),所以两个列表内容不一样
    不足 20 部时用 period 不同的伪随机洗牌补齐
    """
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
    # daily 取 90 天,weekly 取 365 天,确保两边都有内容
    window_days = 90 if period == "daily" else 365

    def parse_date(v):
        d = v.get("date") or ""
        try:
            return _dt.date.fromisoformat(d)
        except Exception:
            return None

    # 给无日期作品一个伪日期:daily 算 7 天前发布,weekly 算 90 天前发布
    # 这样 daily/weekly 的"近期度分"会自然分桶
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

    # 按"近期度分 + 伪随机微扰"排序,保证 daily/weekly 顺序有差异
    import hashlib

    salt = "d" if period == "daily" else "w"
    # daily 每小时换一次种子,weekly 每天换一次,让列表感觉"会动"
    if period == "daily":
        seed = int(today.strftime("%Y%m%d%H"))
    else:
        seed = int(today.strftime("%Y%m%d"))

    def score(v, d):
        h = hashlib.md5(f"{salt}|{seed}|{v.get('code') or ''}".encode()).hexdigest()
        return hot_score(v, d) + int(h[:6], 16) / 0xFFFFFF  # 0~1 抖动

    ranked = sorted(with_date, key=lambda x: score(x[0], x[1]), reverse=True)
    # 如果带日期的不够 20,再从无日期里按 period 洗牌补
    if len(ranked) < 20:
        no_date = [v for v in videos if parse_date(v) is None]

        # 伪随机洗牌
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


def _scrape_trending(source: str, period: str) -> dict:
    """返回 {source, period, items, error}"""
    if source == "missav":
        # missav 没有稳定的 /daily /weekly 路径,统一从首页拉"热门"区
        url = "https://missav.ws/"
        html = _trend_http_get(url, referer="https://missav.ws/")
        items = _parse_missav_trending(html, period)
        if not items:
            items = _local_fallback_trending(source, period)
    else:
        # jable: 远端能拉到的代码,只保留本地 jable_data.json 里也有的,
        # 这样点击可以在结果区加载并播放;不够 20 部再用本地 fallback 补齐
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
            # 远端不够,用本地热门补齐(同样确保 code 都在本地)
            local_items = _local_fallback_trending(source, period)
            seen = {it["code"] for it in items}
            for it in local_items:
                if it["code"] in seen:
                    continue
                items.append(it)
                seen.add(it["code"])
                if len(items) >= 20:
                    break
    items = [{**it, "date": it.get("date", "")} for it in items]
    return {
        "source": source,
        "period": period,
        "items": items,
        "fetchedAt": int(time.time() * 1000),
    }


def _get_trending(source: str, period: str) -> dict:
    path = _trend_path(source, period)
    # 1) 命中磁盘缓存
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
    # 2) 拉取
    with TREND_LOCK:
        # 锁内再次检查(防并发)
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


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        if self.path.startswith("/img/"):
            self.proxy_img()
        elif self.path.startswith("/sync_state.json"):
            self.serve_sync_state()
        elif self.path == "/stats":
            self._send_text(self.stats())
        elif self.path.startswith("/play/"):
            self.proxy_play()
        elif self.path.startswith("/jable_codes"):
            self.serve_jable_codes()
        elif self.path.startswith("/browser_hls_map_upsert"):
            self.serve_browser_hls_map_upsert()
        elif self.path.startswith("/trending"):
            self.serve_trending()
        elif self.path.startswith("/trend_preview/"):
            self.serve_trend_preview()
        elif self.path in ("/", "/index.html"):
            self.serve_index()
        elif self.path.startswith("/picker_data.json"):
            data = (ROOT / "picker_data.json").read_bytes()
            self._send_gzip(data, "application/json", "no-cache")
        elif self.path.startswith("/jable_data.json"):
            data = (ROOT / "jable_data.json").read_bytes()
            self._send_gzip(data, "application/json", "no-cache")
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith("/sync_state"):
            self.save_sync_state()
        else:
            self.send_response(404)
            self.end_headers()

    def serve_sync_state(self):
        if not SYNC_STATE_FILE.is_file():
            self._send_gzip(
                b'{"version":1,"updatedAt":0}',
                "application/json; charset=utf-8",
                "no-cache",
            )
            return
        data = SYNC_STATE_FILE.read_bytes()
        self._send_gzip(data, "application/json; charset=utf-8", "no-cache")

    def serve_jable_codes(self):
        try:
            data = json.loads((ROOT / "jable_data.json").read_text(encoding="utf-8"))
            codes = [
                v.get("code", "").lower()
                for v in data.get("videos", [])
                if v.get("code")
            ]
        except Exception:
            codes = []
        body = json.dumps({"codes": codes}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_browser_hls_map_upsert(self):
        from urllib.parse import urlparse, parse_qs

        q = parse_qs(urlparse(self.path).query)
        code = (q.get("code", [""])[0] or "").lower().strip()
        hls_url = (q.get("hls", [""])[0] or "").strip()
        if not code or not hls_url:
            self.send_response(400)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return
        data = _read_browser_hls_map()
        data[code] = hls_url
        BROWSER_HLS_MAP_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        body = json.dumps({"ok": True, "code": code}, ensure_ascii=False).encode(
            "utf-8"
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def save_sync_state(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        if length <= 0:
            self.send_response(400)
            self.end_headers()
            return
        try:
            body = self.rfile.read(length)
            # 轻量校验 JSON
            payload = json.loads(body.decode("utf-8"))
            payload["updatedAt"] = int(time.time() * 1000)
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            tmp = SYNC_STATE_FILE.with_suffix(".json.tmp")
            tmp.write_bytes(data)
            os.replace(tmp, SYNC_STATE_FILE)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        except Exception:
            self.send_response(500)
            self.end_headers()

    def proxy_play(self):
        """代理 jable 视频 m3u8 + ts 分片
        路径规则:
          /play/<code>/playlist.m3u8  -> 抓 jable 视频页,提取 hlsUrl,返回 m3u8 内容
          /play/<code>/<segment>.ts   -> 从 hlsUrl 所在域名代理 .ts 分片(免跨域)
        """
        global _PLAY, _PLAY_FAIL
        # path: /play/<code>/playlist.m3u8  或  /play/<code>/<seg>.ts
        rest = self.path[len("/play/") :]
        parts = rest.split("/", 1)
        if len(parts) < 2:
            self._send_placeholder()
            return
        code, sub = parts
        code = code.lower()
        # 缓存
        cache_root = CACHE_DIR / "play" / code
        m3u8_path = cache_root / "playlist.m3u8"
        meta_path = cache_root / "meta.json"

        if sub == "playlist.m3u8":
            if (
                m3u8_path.is_file()
                and (time.time() - m3u8_path.stat().st_mtime) < CACHE_OK_TTL
            ):
                _PLAY += 1
                self._send_m3u8(m3u8_path, code)
                return
            # 抓 jable 视频页拿 hlsUrl
            hls_url = self._fetch_jable_hlsurl(code)
            if not hls_url:
                _PLAY_FAIL += 1
                self._send_404()
                return
            # 抓 m3u8 内容
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
                # 缓存 m3u8 + meta
                cache_root.mkdir(parents=True, exist_ok=True)
                m3u8_path.write_bytes(data)
                meta_path.write_text(hls_url, encoding="utf-8")
                # 后台延迟预热:8 秒后预热第 21~80 片(不抢 hls.js 开头)
                with _PREFETCH_LOCK:
                    already = code in _PREFETCHED
                    _PREFETCHED.add(code)
                if not already:
                    threading.Thread(
                        target=_prefetch_ts,
                        args=(code, m3u8_path, meta_path, hls_url),
                        daemon=True,
                    ).start()
                self._send_m3u8_bytes(data, code, hls_url)
                return
            except Exception as e:
                _PLAY_FAIL += 1
                self._send_404()
                return
        else:
            # .ts 分片(走 curl_cffi 走代理 7890,本机直连被墙)
            if not meta_path.is_file():
                self._send_404()
                return
            hls_url = meta_path.read_text(encoding="utf-8").strip()
            ts_url = hls_url.rsplit("/", 1)[0] + "/" + sub
            ts_cache = cache_root / sub
            # 磁盘缓存:已下载的 ts 直接返回(高倍速重复请求/seek 回看时秒回)
            if ts_cache.is_file():
                data = ts_cache.read_bytes()
            else:
                lock_key = code + "/" + sub
                if not _acquire_ts_lock(lock_key):
                    # 已有线程(预热)在下载该分片,等待完成后读缓存
                    _wait_ts_lock(lock_key, 30)
                    if ts_cache.is_file():
                        data = ts_cache.read_bytes()
                    else:
                        self._send_404()
                        return
                else:
                    try:
                        from curl_cffi import requests as creq

                        r = creq.get(
                            ts_url,
                            impersonate="chrome",
                            proxy="http://127.0.0.1:7890",
                            timeout=15,
                            headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                                "Referer": "https://jable.tv/",
                                "Origin": "https://jable.tv",
                            },
                        )
                        if r.status_code != 200:
                            _release_ts_lock(lock_key)
                            self._send_404()
                            return
                        data = r.content
                        try:
                            tmp = ts_cache.with_suffix(".ts.tmp")
                            tmp.write_bytes(data)
                            os.replace(tmp, ts_cache)
                        except Exception:
                            pass
                    except Exception:
                        _release_ts_lock(lock_key)
                        self._send_404()
                        return
                    _release_ts_lock(lock_key)
            self.send_response(200)
            self.send_header("Content-Type", "video/mp2t")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

    def _send_m3u8(self, path: Path, code: str):
        data = path.read_bytes()
        meta_path = path.parent / "meta.json"
        hls_url = (
            meta_path.read_text(encoding="utf-8").strip() if meta_path.is_file() else ""
        )
        self._send_m3u8_bytes(data, code, hls_url)

    def _send_m3u8_bytes(self, data: bytes, code: str, hls_url: str):
        # 把 m3u8 里的相对路径 .ts 改写成 /play/<code>/<name>.ts
        try:
            text = data.decode("utf-8", errors="ignore")
            lines = []
            for line in text.split("\n"):
                stripped = line.strip()
                if (
                    stripped
                    and not stripped.startswith("#")
                    and stripped.endswith(".ts")
                ):
                    lines.append(f"/play/{code}/{stripped}")
                else:
                    lines.append(line)
            text = "\n".join(lines).encode("utf-8")
        except Exception:
            text = data
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        self.send_header("Content-Length", str(len(text)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(text)

    def _send_404(self):
        try:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"not found")
        except Exception:
            pass

    def _fetch_jable_hlsurl(self, code: str) -> str:
        """用 curl_cffi 抓 jable 视频页,提取 hlsUrl(m3u8 真实地址)"""
        try:
            from curl_cffi import requests as creq
        except ImportError:
            return ""
        try:
            r = creq.get(
                f"https://jable.tv/videos/{code}/",
                impersonate="chrome",
                proxy="http://127.0.0.1:7890",
                timeout=20,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                    "Referer": "https://jable.tv/",
                },
            )
        except Exception:
            return ""
        if r.status_code != 200:
            return ""
        html = r.text
        if "Just a moment" in html or "cf-browser-verification" in html:
            return ""
        m = re.search(
            r'hlsUrl["\']?\s*[:=]\s*["\'](https?://[^"\']+\.m3u8[^"\']*)', html
        )
        return m.group(1) if m else ""

    def _send_text(self, text: str):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    # ---- 每日 / 每周热门 ----
    def serve_trending(self):
        """/trending?source=missav|jable&period=daily|weekly"""
        from urllib.parse import urlparse, parse_qs

        q = parse_qs(urlparse(self.path).query)
        source = (q.get("source", ["missav"])[0] or "missav").lower()
        period = (q.get("period", ["daily"])[0] or "daily").lower()
        if source not in ("missav", "jable"):
            source = "missav"
        if period not in ("daily", "weekly"):
            period = "daily"
        try:
            payload = _get_trending(source, period)
        except Exception as e:
            payload = {
                "source": source,
                "period": period,
                "items": [],
                "error": repr(e)[:120],
            }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_trend_preview(self):
        """/trend_preview/<source>/<code>.mp4  代理 missav 的 fourhoi 预览 mp4(免 403)"""
        from urllib.parse import urlparse, parse_qs

        rest = self.path[len("/trend_preview/") :]
        if rest.endswith(".mp4"):
            rest = rest[:-4]
        parts = rest.split("/", 1)
        if len(parts) < 2:
            self.send_response(404)
            self.end_headers()
            return
        source, code = parts[0].lower(), parts[1].lower()
        if source not in ("missav", "jable"):
            self.send_response(404)
            self.end_headers()
            return
        if source == "missav":
            upstream = f"https://fourhoi.com/{code}/preview.mp4"
            referer = "https://missav.ws/"
        else:
            upstream = f"https://fourhoi.com/{code}/preview.mp4"
            referer = "https://jable.tv/"
        # 磁盘缓存(7 天)
        cache_path = CACHE_DIR / "trend_preview" / f"{source}_{code}.mp4"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if (
            cache_path.is_file()
            and (time.time() - cache_path.stat().st_mtime) < CACHE_OK_TTL
        ):
            data = cache_path.read_bytes()
            self._send_mp4(data, code, source)
            return
        data = b""
        # 优先 curl_cffi + 7890
        try:
            from curl_cffi import requests as creq

            r = creq.get(
                upstream,
                impersonate="chrome",
                proxy="http://127.0.0.1:7890",
                timeout=20,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                    "Referer": referer,
                    "Accept": "*/*",
                },
            )
            if r.status_code == 200 and r.content:
                data = r.content
        except Exception:
            pass
        # 失败回退 urllib 直连
        if not data:
            try:
                req = urllib.request.Request(
                    upstream,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                        "Referer": referer,
                    },
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = resp.read()
            except Exception:
                pass
        if not data:
            self.send_response(502)
            self.end_headers()
            return
        try:
            tmp = cache_path.with_suffix(".mp4.tmp")
            tmp.write_bytes(data)
            os.replace(tmp, cache_path)
        except Exception:
            pass
        self._send_mp4(data, code, source)

    def _send_mp4(self, data: bytes, code: str, source: str):
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def serve_index(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        html = re.sub(r'<script id="DATA".*?</script>', "", html, flags=re.DOTALL)
        self._send_gzip(html.encode(), "text/html; charset=utf-8", "no-cache")

    def _send_gzip(self, data, mime, cache="public, max-age=86400"):
        accept = self.headers.get("Accept-Encoding", "")
        if "gzip" in accept:
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6) as f:
                f.write(data)
            compressed = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(compressed)))
            self.send_header("Cache-Control", cache)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(compressed)
        else:
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", cache)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

    def proxy_img(self):
        global _HIT, _MISS, _FAIL
        raw = self.path[5:]  # 去掉 '/img/'
        if not raw or ".." in raw:
            self._send_placeholder()
            return
        if raw.startswith("http://"):
            raw = raw[7:]
        if raw.startswith("https://"):
            raw = raw[8:]
        if "/" not in raw:
            self._send_placeholder()
            return
        domain, _, sub = raw.partition("/")
        url = f"https://{domain}/{sub}"
        cache_path = CACHE_DIR / domain / sub.replace("/", os.sep)
        neg_path = CACHE_DIR / domain / (sub.replace("/", os.sep) + ".fail")

        # 命中磁盘缓存(成功)
        if cache_path.is_file():
            age = time.time() - cache_path.stat().st_mtime
            if age < CACHE_OK_TTL:
                _HIT += 1
                self._send_file(cache_path)
                return
        # 命中磁盘缓存(近期失败) → 直接占位,不重试
        if neg_path.is_file():
            age = time.time() - neg_path.stat().st_mtime
            if age < CACHE_FAIL_TTL:
                _FAIL += 1
                self._send_placeholder()
                return
        _MISS += 1
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "image/*,video/*",
            }
            if "jable.tv" in domain:
                from curl_cffi import requests as creq

                r = creq.get(
                    url,
                    impersonate="chrome",
                    proxy="http://127.0.0.1:7890",
                    timeout=15,
                    headers={**headers, "Referer": "https://jable.tv/"},
                )
                if r.status_code != 200:
                    raise OSError(f"image status {r.status_code}")
                data = r.content
                ct = r.headers.get("Content-Type", "image/jpeg")
            else:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = resp.read()
                    ct = resp.headers.get("Content-Type", "image/jpeg")
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(data)
            except OSError:
                pass
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", f"public, max-age={CACHE_OK_TTL}")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
            self._maybe_evict()
        except (urllib.error.URLError, TimeoutError, OSError):
            _FAIL += 1
            try:
                neg_path.parent.mkdir(parents=True, exist_ok=True)
                neg_path.touch()
            except OSError:
                pass
            try:
                self._send_placeholder()
            except (BrokenPipeError, ConnectionAbortedError):
                pass

    def _send_file(self, path: Path):
        data = path.read_bytes()
        ct = "image/jpeg"
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            ct = "image/png"
        elif data[:3] == b"GIF":
            ct = "image/gif"
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            ct = "image/webp"
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", f"public, max-age={CACHE_OK_TTL}")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _send_placeholder(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(PLACEHOLDER_PNG)))
        self.send_header("Cache-Control", f"public, max-age={CACHE_FAIL_TTL}")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(PLACEHOLDER_PNG)

    def _maybe_evict(self):
        try:
            files = [p for p in CACHE_DIR.rglob("*") if p.is_file()]
            total = sum(p.stat().st_size for p in files)
        except OSError:
            return
        if total <= CACHE_MAX_BYTES:
            return
        files.sort(key=lambda p: p.stat().st_mtime)
        for p in files[: max(1, len(files) // 10)]:
            try:
                p.unlink()
            except OSError:
                pass

    def stats(self):
        try:
            files = [p for p in CACHE_DIR.rglob("*") if p.is_file()]
            count = len(files)
            total = sum(p.stat().st_size for p in files)
            size_mb = total / 1024 / 1024
        except OSError:
            count, size_mb = 0, 0.0
        return f"缓存 {count} 张 / {size_mb:.1f}MB · 图片 {_HIT}/{_MISS}/{_FAIL} · /play {_PLAY}/{_PLAY_FAIL}"

    def end_headers(self):
        super().end_headers()

    def log_message(self, format, *args):
        msg = format % args
        if "img/" in msg or ".json" in msg:
            return
        print(f"  {self.address_string()}  {msg}")


def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


ip = get_lan_ip()
CACHE_DIR.mkdir(exist_ok=True)
print(
    f"\n  封面/头像已走本地代理 + 磁盘缓存 ({CACHE_MAX_BYTES // 1024 // 1024}MB 上限)"
)
print(f"  缓存目录: {CACHE_DIR}")
print(f"  本机:  http://localhost:{PORT}")
print(f"  手机:  http://{ip}:{PORT}")
print(f"  状态:  http://localhost:{PORT}/stats")
print(f"  按 Ctrl+C 停止\n")

with http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止")
        sys.exit(0)
