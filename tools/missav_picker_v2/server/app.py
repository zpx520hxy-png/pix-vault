import http.server
import gzip
import io
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .config import (
    ROOT,
    PORT,
    PLACEHOLDER_PNG,
    CACHE_OK_TTL,
    CACHE_FAIL_TTL,
    DATA_FILES,
    get_lan_ip,
)
from .cache import (
    get_counters,
    get_cache_size,
    read_browser_hls_map,
    upsert_browser_hls,
    evict_img_cache,
)
from .sync_state import read_sync_state, save_sync_state, get_jable_codes
from .play_proxy import proxy_playlist, proxy_ts_segment, rewrite_m3u8_ts_paths
from .img_proxy import proxy_img, _detect_ct
from .trending import get_trending


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)

        if path.startswith("/img/"):
            self._handle_img(path[5:])
        elif path.startswith("/sync_state.json"):
            self._handle_sync_state()
        elif path == "/stats":
            self._handle_stats()
        elif path.startswith("/play/"):
            self._handle_play(path[6:])
        elif path.startswith("/jable_codes"):
            self._handle_jable_codes()
        elif path.startswith("/browser_hls_map_upsert"):
            self._handle_browser_hls_upsert(query)
        elif path.startswith("/trending"):
            self._handle_trending(query)
        elif path.startswith("/trend_preview/"):
            self._handle_trend_preview(path[len("/trend_preview/") :])
        elif path in ("/", "/index.html"):
            self._handle_index()
        elif path.startswith("/picker_data.json"):
            self._handle_data_file("missav", "application/json")
        elif path.startswith("/jable_data.json"):
            self._handle_data_file("jable", "application/json")
        elif path.startswith("/picker_index.json"):
            self._handle_data_file("index", "application/json")
        elif path.startswith("/app.css"):
            self._serve_static_file(ROOT / "app.css", "text/css; charset=utf-8")
        elif path.startswith("/app.js"):
            self._serve_static_file(
                ROOT / "app.js", "application/javascript; charset=utf-8"
            )
        else:
            super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/sync_state":
            self._handle_save_sync_state()
        else:
            self.send_response(404)
            self.end_headers()

    # ---- handlers ----

    def _handle_img(self, remainder):
        result, source = proxy_img(remainder)
        if result is None:
            self._send_placeholder()
            return
        data, ct = result
        self._send_bytes(data, ct, CACHE_OK_TTL)

    def _handle_sync_state(self):
        data = read_sync_state()
        self._send_gzip(data, "application/json; charset=utf-8", "no-cache")

    def _handle_stats(self):
        c = get_counters()
        n_img, sz_img = get_cache_size()
        n_play, sz_play = get_cache_size("play")
        body = (
            f"缓存 {n_img} 文件 / {sz_img / 1024 / 1024:.1f}MB"
            f" · 播放缓存 {n_play} 文件 / {sz_play / 1024 / 1024:.1f}MB"
            f" · 图片 {c['hit']}/{c['miss']}/{c['fail']}"
            f" · /play {c['play']}/{c['play_fail']}"
        )
        self._send_text(body)

    def _handle_play(self, rest):
        parts = rest.split("/", 1)
        code = parts[0].lower()
        if not code:
            self._send_404()
            return
        if len(parts) < 2 or parts[1] == "playlist.m3u8":
            data, source = proxy_playlist(code)
            if data is None:
                self._send_404()
                return
            m3u8_text = data.decode("utf-8", errors="ignore")
            rewritten = rewrite_m3u8_ts_paths(m3u8_text, code)
            self._send_bytes(
                rewritten.encode("utf-8"),
                "application/vnd.apple.mpegurl",
                CACHE_OK_TTL,
            )
        else:
            seg_name = parts[1]
            data, source = proxy_ts_segment(code, seg_name)
            if data is None:
                self._send_404()
                return
            self._send_bytes(data, "video/mp2t", CACHE_OK_TTL)

    def _handle_jable_codes(self):
        codes = get_jable_codes()
        body = json.dumps({"codes": codes}, ensure_ascii=False).encode("utf-8")
        self._send_json(body)

    def _handle_browser_hls_upsert(self, query):
        code = (query.get("code", [""])[0] or "").lower().strip()
        hls_url = (query.get("hls", [""])[0] or "").strip()
        if not code or not hls_url:
            self.send_response(400)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return
        upsert_browser_hls(code, hls_url)
        body = json.dumps({"ok": True, "code": code}, ensure_ascii=False).encode(
            "utf-8"
        )
        self._send_json(body)

    def _handle_trending(self, query):
        source = (query.get("source", ["missav"])[0] or "missav").lower()
        period = (query.get("period", ["daily"])[0] or "daily").lower()
        if source not in ("missav", "jable"):
            source = "missav"
        if period not in ("daily", "weekly"):
            period = "daily"
        try:
            payload = get_trending(source, period)
        except Exception as e:
            payload = {
                "source": source,
                "period": period,
                "items": [],
                "error": repr(e)[:120],
            }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_json(body)

    def _handle_trend_preview(self, rest):
        if rest.endswith(".mp4"):
            rest = rest[:-4]
        parts = rest.split("/", 1)
        if len(parts) < 2:
            self._send_404()
            return
        source, code = parts[0].lower(), parts[1].lower()
        upstream = f"https://fourhoi.com/{code}/preview.mp4"
        referer = "https://missav.ws/" if source == "missav" else "https://jable.tv/"
        cache_dir = CACHE_DIR / "trend_preview"
        cache_path = cache_dir / f"{source}_{code}.mp4"
        if (
            cache_path.is_file()
            and (time.time() - cache_path.stat().st_mtime) < CACHE_OK_TTL
        ):
            data = cache_path.read_bytes()
            self._send_bytes(data, "video/mp4", CACHE_OK_TTL)
            return
        data = b""
        from .config import proxy_kwargs

        try:
            from curl_cffi import requests as creq

            r = creq.get(
                upstream,
                impersonate="chrome",
                timeout=20,
                **proxy_kwargs(),
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": referer,
                },
            )
            if r.status_code == 200 and r.content:
                data = r.content
        except Exception:
            pass
        if not data:
            try:
                req = urllib.request.Request(
                    upstream,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Referer": referer,
                    },
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = resp.read()
            except Exception:
                self.send_response(502)
                self.end_headers()
                return
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(data)
        except Exception:
            pass
        self._send_bytes(data, "video/mp4", CACHE_OK_TTL)

    def _handle_index(self):
        index_path = ROOT / "index.html"
        if not index_path.is_file():
            self._send_text("index.html not found")
            return
        html = index_path.read_text(encoding="utf-8")
        html = re.sub(
            r'<script id="DATA"[^>]*>.*?</script>',
            "",
            html,
            flags=re.S,
        )
        self._send_gzip(html.encode("utf-8"), "text/html; charset=utf-8", "no-cache")

    def _handle_data_file(self, key, content_type):
        data_file = DATA_FILES.get(key)
        if not data_file or not data_file.is_file():
            self._send_404()
            return
        data = data_file.read_bytes()
        self._send_gzip(data, content_type, "no-cache")

    def _handle_save_sync_state(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0 or length > 10 * 1024 * 1024:
                self.send_response(400)
                self.end_headers()
                return
            body = self.rfile.read(length)
            ok = save_sync_state(body)
            resp = json.dumps({"ok": ok}).encode("utf-8")
            self._send_json(resp)
        except Exception:
            self.send_response(500)
            self.end_headers()

    def _serve_static_file(self, path, content_type):
        if not path.is_file():
            self._send_404()
            return
        data = path.read_bytes()
        self._send_gzip(data, content_type, "public, max-age=3600")

    # ---- helpers ----

    def _send_bytes(self, data, content_type, cache_control):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def _send_json(self, data):
        self._send_bytes(data, "application/json; charset=utf-8", "no-cache")

    def _send_text(self, text):
        data = text.encode("utf-8")
        self._send_bytes(data, "text/plain; charset=utf-8", "no-cache")

    def _send_gzip(self, data, content_type, cache_control):
        accept = self.headers.get("Accept-Encoding", "")
        if "gzip" in accept and len(data) > 1024:
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
                gz.write(data)
            data = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Cache-Control", cache_control)
            self.end_headers()
        else:
            self._send_bytes(data, content_type, cache_control)
            return
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def _send_placeholder(self):
        self._send_bytes(PLACEHOLDER_PNG, "image/png", CACHE_FAIL_TTL)

    def _send_404(self):
        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "9")
        self.end_headers()
        self.wfile.write(b"not found")

    def end_headers(self):
        super().end_headers()

    def log_message(self, format, *args):
        msg = format % args
        if "img/" in msg or ".json" in msg:
            return
        print(f"  {self.address_string()}  {msg}")


def run():
    from .config import CACHE_DIR, PORT, get_lan_ip

    CACHE_DIR.mkdir(exist_ok=True)
    ip = get_lan_ip()
    print(f"\n  MissAV Picker V2 (模块化)")
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
