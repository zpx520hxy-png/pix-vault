"""MissAV Picker 局域网服务器(含图片代理+磁盘缓存+gzip)"""

import http.server
import socket
import sys
import gzip
import io
import os
import re
import time
import hashlib
import urllib.request
import urllib.error
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PORT = 8699
ROOT = Path(__file__).parent
CACHE_DIR = ROOT / ".img_cache"
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


def _prefetch_ts(
    code: str, m3u8_path: Path, meta_path: Path, hls_url: str, limit: int = 20
):
    """后台并发预热 ts 分片:解析 m3u8,下载前 limit 个未缓存的分片到磁盘。
    只预热开头 20 片(约 80 秒),延迟 3 秒启动让封面/数据先加载完。
    seek 到未预热区时 hls.js 会触发对应 ts 请求,server 再缓存。"""
    time.sleep(3)  # 让封面图、m3u8、数据等先加载完,避免抢占带宽
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
    if not segs:
        return
    # 只取前 limit 个未缓存的
    todo = []
    for name in segs:
        if not (cache_root / name).is_file():
            todo.append(name)
            if len(todo) >= limit:
                break
    if not todo:
        return
    base_url = hls_url.rsplit("/", 1)[0]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Referer": "https://jable.tv/",
        "Origin": "https://jable.tv",
    }

    def _dl(name):
        ts_cache = cache_root / name
        if ts_cache.is_file():
            return
        ts_url = base_url + "/" + name
        try:
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

    # 并发 2 路预热(控制带宽,避免占满导致封面/数据请求失败)
    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            list(ex.map(_dl, todo))
    except Exception:
        pass

    # 并发 6 路预热(每线程独立请求,curl_cffi 线程安全)
    try:
        with ThreadPoolExecutor(max_workers=6) as ex:
            list(ex.map(_dl, segs))
    except Exception:
        pass


# 已预热的 code 集合(避免重复预热)
_PREFETCHED = set()
_PREFETCH_LOCK = threading.Lock()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        if self.path.startswith("/img/"):
            self.proxy_img()
        elif self.path == "/stats":
            self._send_text(self.stats())
        elif self.path.startswith("/play/"):
            self.proxy_play()
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

    def proxy_play(self):
        """代理 jable 视频 m3u8 + ts 分片
        路径规则:
          /play/<code>/playlist.m3u8  -> 抓 jable 视频页,提取 hlsUrl,返回 m3u8 内容
          /play/<code>/<segment>.ts   -> 从 hlsUrl 所在域名代理 .ts 分片(免跨域)
        """
        global _PLAY
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
                # 后台并发预热 ts 分片(hls.js 请求时命中本地缓存)
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
                    self._send_404()
                    return
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
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "image/*,video/*",
                },
            )
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
            self._send_placeholder()

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
