import http.server
import gzip
import io
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import urllib.request

from .config import (
    ROOT,
    PORT,
    PLACEHOLDER_PNG,
    CACHE_OK_TTL,
    CACHE_FAIL_TTL,
    TREND_MEDIA_TTL,
    TREND_PREVIEW_CACHE_DIR,
    CACHE_DIR,
    DATA_FILES,
    FAVORITE_MEDIA_CACHE_DIR,
    get_lan_ip,
    proxy_kwargs,
)
from .cache import (
    get_counters,
    get_cache_size,
    read_browser_hls_map,
    upsert_browser_hls,
    evict_img_cache,
)
from .sync_state import read_sync_state, save_sync_state, get_jable_codes
from .play_proxy import (
    proxy_playlist,
    proxy_ts_segment,
    rewrite_m3u8_ts_paths,
    request_play,
    get_play_status,
    is_play_cache_complete,
)
from .img_proxy import proxy_img, _detect_ct
from .trending import (
    get_trending,
    get_trending_progress,
    import_manual_jable_trending,
    trending_metadata_path,
)


FOURHOI_REFERER = "https://missav.ws/"


def _favorite_media_dir(source, code):
    safe_source = re.sub(r"[^a-z0-9_-]", "", source.lower())
    safe_code = re.sub(r"[^a-z0-9_-]", "", code.lower())
    if safe_source not in ("missav", "jable") or not safe_code:
        return None
    return FAVORITE_MEDIA_CACHE_DIR / safe_source / safe_code


_GIF_PREP_LOCK = set()
_GIF_PREP_LOCK_GUARD = threading.Lock()


def _prepare_favorite_gif(source, code):
    cache_dir = _favorite_media_dir(source, code)
    if not cache_dir:
        return
    gif_path = cache_dir / "cover.gif"
    if gif_path.is_file() and gif_path.stat().st_size > 0:
        return
    key = f"{source}:{code}".lower()
    with _GIF_PREP_LOCK_GUARD:
        if key in _GIF_PREP_LOCK:
            return
        _GIF_PREP_LOCK.add(key)
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        preview_path = cache_dir / "preview.mp4"
        if not preview_path.is_file() or not preview_path.stat().st_size:
            cached_previews = [
                path
                for path in cache_dir.glob("*preview.mp4")
                if path.is_file() and path.stat().st_size > 0
            ]
            if cached_previews:
                preview_path = max(
                    cached_previews, key=lambda path: path.stat().st_mtime
                )
        if not preview_path.is_file() or not preview_path.stat().st_size:
            upstream = f"https://fourhoi.com/{code.lower()}/preview.mp4"
            data = b""
            try:
                from curl_cffi import requests as creq

                response = creq.get(
                    upstream,
                    impersonate="chrome",
                    timeout=20,
                    **proxy_kwargs(),
                    headers={"Referer": FOURHOI_REFERER},
                )
                if response.status_code == 200:
                    data = response.content
            except Exception:
                pass
            if not data:
                try:
                    request = urllib.request.Request(
                        upstream, headers={"Referer": FOURHOI_REFERER}
                    )
                    with urllib.request.urlopen(request, timeout=20) as response:
                        data = response.read()
                except Exception:
                    pass
            if data:
                temp_preview = preview_path.with_suffix(".mp4.tmp")
                temp_preview.write_bytes(data)
                os.replace(temp_preview, preview_path)
        input_path = preview_path
        input_is_image = False
        if not input_path.is_file() or not input_path.stat().st_size:
            cached_images = [
                path
                for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp")
                for path in cache_dir.glob(pattern)
                if path.is_file() and path.stat().st_size > 0
            ]
            if not cached_images:
                return
            input_path = max(cached_images, key=lambda path: path.stat().st_mtime)
            input_is_image = True
        temp_gif = cache_dir / "cover.tmp.gif"
        command = [
            "ffmpeg",
            "-y",
            "-ss",
            "0",
        ]
        if input_is_image:
            command.extend(["-loop", "1"])
        command.extend(
            [
                "-t",
                "3",
                "-i",
                str(input_path),
                "-vf",
                "fps=8,scale=360:-2:flags=lanczos",
                "-loop",
                "0",
                "-f",
                "gif",
                str(temp_gif),
            ]
        )
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=False,
        )
        if result.returncode == 0 and temp_gif.is_file() and temp_gif.stat().st_size:
            os.replace(temp_gif, gif_path)
        else:
            temp_gif.unlink(missing_ok=True)
    except Exception:
        pass
    finally:
        with _GIF_PREP_LOCK_GUARD:
            _GIF_PREP_LOCK.discard(key)


def _rebuild_index():
    import collections

    f = DATA_FILES.get("missav")
    if not f or not f.is_file():
        return
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        videos = data.get("videos", [])
        actresses = sorted(
            set(
                a.strip()
                for v in videos
                for a in (v.get("actresses") or [])
                if a.strip()
            )
        )
        tags = sorted(
            set(t.strip() for v in videos for t in (v.get("tags") or []) if t.strip())
        )
        tag_counts = collections.Counter()
        for v in videos:
            for t in set(t.strip() for t in (v.get("tags") or []) if t.strip()):
                tag_counts[t] += 1
        idx = DATA_FILES.get("index")
        if idx:
            idx.write_text(
                json.dumps(
                    {
                        "actresses": actresses,
                        "actress_groups": data.get("actress_groups", {}),
                        "actress_avatars": data.get("actress_avatars", {}),
                        "actress_display": data.get("actress_display", {}),
                        "actress_aid": data.get("actress_aid", {}),
                        "tags": tags,
                        "tag_counts": dict(tag_counts),
                        "total_videos": len(videos),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
    except Exception:
        pass


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)

        if path.startswith("/img/"):
            self._handle_img(path[5:], query)
        elif path == "/health":
            self._handle_health()
        elif path.startswith("/sync_state.json"):
            self._handle_sync_state()
        elif path == "/stats":
            self._handle_stats()
        elif path.startswith("/cache_plan"):
            self._handle_cache_plan()
        elif path.startswith("/playable_jable"):
            self._handle_playable_jable()
        elif path.startswith("/play/"):
            self._handle_play(path[6:], query)
        elif path.startswith("/jable_codes"):
            self._handle_jable_codes()
        elif path.startswith("/browser_hls_map_upsert"):
            self._handle_browser_hls_upsert(query)
        elif path.startswith("/favorite_cover_gif/"):
            self._handle_favorite_cover_gif(path[len("/favorite_cover_gif/") :])
        elif path.startswith("/trending_progress"):
            self._handle_trending_progress(query)
        elif path.startswith("/trending"):
            self._handle_trending(query)
        elif path.startswith("/trend_preview/"):
            self._handle_trend_preview(path[len("/trend_preview/") :], query)
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
        elif path == "/remove_video":
            self._handle_remove_video()
        elif path == "/restore_video":
            self._handle_restore_video()
        elif path == "/add_trending_videos":
            self._handle_add_trending_videos()
        elif path == "/import_jable_trending":
            self._handle_import_jable_trending()
        elif path == "/save_jable_metadata":
            self._handle_save_jable_metadata()
        elif path == "/save_missav_metadata":
            self._handle_save_missav_metadata()
        elif path == "/favorite_media_cache":
            self._handle_favorite_media_cache()
        else:
            self.send_response(404)
            self.end_headers()

    # ---- handlers ----

    def _handle_img(self, remainder, query):
        persistent = (query.get("persist", [""])[0] or "").lower() == "favorite"
        transient = (query.get("cache", [""])[0] or "").lower() == "trend"
        source_name = query.get("source", [""])[0] or ""
        code = query.get("code", [""])[0] or ""
        result, source = proxy_img(
            remainder, persistent, source_name, code, transient=transient
        )
        if result is None:
            self._send_placeholder()
            return
        data, ct = result
        # 文件级 304 支持
        safe_source = re.sub(r"[^a-z0-9_-]", "", source_name.lower())
        safe_code = re.sub(r"[^a-z0-9_-]", "", code.lower())
        cache_path = None
        cache_ttl = CACHE_OK_TTL
        if persistent and safe_source and safe_code:
            cache_path = (
                FAVORITE_MEDIA_CACHE_DIR
                / safe_source
                / safe_code
                / remainder.replace("/", "_")
            )
            # Favorite covers, including animated GIF files, are local assets.
            # The browser may retain them for a year; the server keeps them
            # until the corresponding favorite is explicitly removed.
            cache_ttl = 365 * 24 * 3600
        elif transient:
            cache_path = (
                TREND_PREVIEW_CACHE_DIR / "images" / remainder.replace("/", "_")
            )
            cache_ttl = TREND_MEDIA_TTL
        if cache_path and cache_path.is_file():
            mtime = cache_path.stat().st_mtime
            last_mod = self._http_date(mtime)
            if self.headers.get("If-Modified-Since") == last_mod:
                self.send_response(304)
                self.end_headers()
                return
            self._send_bytes(
                data,
                ct,
                cache_ttl,
                extra_headers={"Last-Modified": last_mod},
            )
        else:
            self._send_bytes(data, ct, cache_ttl)

    def _handle_sync_state(self):
        data = read_sync_state()
        self._send_gzip(data, "application/json; charset=utf-8", "no-cache")

    def _handle_health(self):
        body = json.dumps(
            {
                "ok": True,
                "service": "missav-picker-v2",
                "time": int(time.time()),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        self._send_json(body)

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

    def _handle_cache_plan(self):
        from .prewarm import read_plan, run_prewarm_once

        action = parse_qs(urlparse(self.path).query).get("action", [""])[0]
        if action == "run":
            summary = run_prewarm_once()
            body = json.dumps(
                {"ok": True, "summary": summary}, ensure_ascii=False
            ).encode("utf-8")
            self._send_json(body)
            return
        plan = read_plan()
        if not plan:
            self._send_json(json.dumps({"ok": True, "plan": None}).encode("utf-8"))
            return
        n_img, sz_img = get_cache_size()
        n_play, sz_play = get_cache_size("play")
        plan["current_cache"] = {
            "image_files": n_img,
            "image_mb": round(sz_img / 1024 / 1024, 1),
            "play_files": n_play,
            "play_mb": round(sz_play / 1024 / 1024, 1),
        }
        body = json.dumps({"ok": True, "plan": plan}, ensure_ascii=False).encode(
            "utf-8"
        )
        self._send_json(body)

    def _handle_playable_jable(self):
        data_file = DATA_FILES.get("jable")
        playable = []
        play_root = CACHE_DIR / "play"
        # 这里只展示“真正完整可播”的作品：playlist + AES key + 分片都在本地
        playable_codes = set()
        if play_root.is_dir():
            for p in play_root.iterdir():
                if p.is_dir() and is_play_cache_complete(p.name.lower()):
                    playable_codes.add(p.name.lower())
        try:
            data = (
                json.loads(data_file.read_text(encoding="utf-8")).get("videos", [])
                if data_file and data_file.is_file()
                else []
            )
        except Exception:
            data = []
        for v in data:
            code = (v.get("code") or "").lower()
            if code and code in playable_codes:
                playable.append(v)
        # 优先按日期倒序,空日期排后
        playable.sort(key=lambda v: v.get("date") or "", reverse=True)
        body = json.dumps(
            {"ok": True, "items": playable[:30]}, ensure_ascii=False
        ).encode("utf-8")
        self._send_json(body)

    def _handle_play(self, rest, query):
        parts = rest.split("/", 1)
        code = parts[0].lower()
        if not code:
            self._send_404()
            return
        if len(parts) < 2:
            self._send_404()
            return
        sub = parts[1]
        persistent = (query.get("persist", [""])[0] or "").lower() == "favorite"
        if sub == "playlist.m3u8":
            data, source = proxy_playlist(code, persistent=persistent)
            if data is None:
                self._send_404()
                return
            m3u8_text = data.decode("utf-8", errors="ignore")
            rewritten = rewrite_m3u8_ts_paths(m3u8_text, code, persistent=persistent)
            self._send_bytes(
                rewritten.encode("utf-8"),
                "application/vnd.apple.mpegurl",
                CACHE_OK_TTL,
            )
        elif sub == "request":
            result = request_play(code, persistent=persistent)
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self._send_json(body)
        elif sub == "status":
            result = get_play_status(code, persistent=persistent)
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self._send_json(body)
        else:
            data, source = proxy_ts_segment(code, sub, persistent=persistent)
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

    def _handle_favorite_cover_gif(self, rest):
        parts = rest.removesuffix(".gif").split("/", 1)
        if len(parts) != 2:
            self._send_404()
            return
        cache_dir = _favorite_media_dir(parts[0], parts[1])
        if not cache_dir:
            self._send_404()
            return
        gif_path = cache_dir / "cover.gif"
        if not gif_path.is_file():
            threading.Thread(
                target=_prepare_favorite_gif,
                args=(parts[0], parts[1]),
                daemon=True,
            ).start()
            self._send_404()
            return
        self._send_bytes(gif_path.read_bytes(), "image/gif", 365 * 24 * 3600)

    def _handle_trending(self, query):
        source = (query.get("source", ["missav"])[0] or "missav").lower()
        period = (query.get("period", ["daily"])[0] or "daily").lower()
        if source not in ("missav", "jable"):
            source = "missav"
        if period not in ("daily", "weekly"):
            period = "daily"
        force = "_" in query or (query.get("force", [""])[0] or "").lower() in (
            "1",
            "true",
            "yes",
        )
        try:
            payload = get_trending(source, period, force=force)
        except Exception as e:
            payload = {
                "source": source,
                "period": period,
                "items": [],
                "error": repr(e)[:120],
            }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_json(body)

    def _handle_trending_progress(self, query):
        source = (query.get("source", ["missav"])[0] or "missav").lower()
        period = (query.get("period", ["daily"])[0] or "daily").lower()
        if source not in ("missav", "jable"):
            source = "missav"
        if period not in ("daily", "weekly"):
            period = "daily"
        body = json.dumps(
            get_trending_progress(source, period), ensure_ascii=False
        ).encode("utf-8")
        self._send_json(body)

    def _handle_import_jable_trending(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0 or length > 512 * 1024:
                self.send_response(400)
                self.end_headers()
                return
            payload = json.loads(self.rfile.read(length))
            period = (payload.get("period") or "daily").lower()
            data = import_manual_jable_trending(period, payload.get("text") or "")
            self._send_json(
                json.dumps({"ok": True, "data": data}, ensure_ascii=False).encode(
                    "utf-8"
                )
            )
        except ValueError as e:
            body = json.dumps(
                {"ok": False, "error": str(e)}, ensure_ascii=False
            ).encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_response(500)
            self.end_headers()

    def _handle_trend_preview(self, rest, query):
        if rest.endswith(".mp4"):
            rest = rest[:-4]
        parts = rest.split("/", 1)
        if len(parts) < 2:
            self._send_404()
            return
        source, code = parts[0].lower(), parts[1].lower()
        persistent = (query.get("persist", [""])[0] or "").lower() == "favorite"
        upstream = f"https://fourhoi.com/{code}/preview.mp4"
        referer = FOURHOI_REFERER
        cache_dir = (
            FAVORITE_MEDIA_CACHE_DIR / source / code
            if persistent
            else TREND_PREVIEW_CACHE_DIR / "videos" / source / code
        )
        cache_ttl = 365 * 24 * 3600 if persistent else TREND_MEDIA_TTL
        cache_path = cache_dir / "preview.mp4"
        cache_is_fresh = cache_path.is_file() and (
            persistent or (time.time() - cache_path.stat().st_mtime) < cache_ttl
        )
        if cache_is_fresh:
            data = cache_path.read_bytes()
            self._send_bytes(data, "video/mp4", cache_ttl)
            return
        data = b""
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
        self._send_bytes(data, "video/mp4", cache_ttl)

    def _handle_index(self):
        index_path = ROOT / "index.html"
        if not index_path.is_file():
            self._send_text("index.html not found")
            return
        html = index_path.read_text(encoding="utf-8")
        # 只有当 <script id="DATA"> 还是 __DATA_JSON_PLACEHOLDER__ 时才删掉这段
        # (兜底: 没跑 assemble 时不让浏览器拿到 placeholder 字符串)
        # 跑过 assemble 后,这里已经是真实 JSON,保留内嵌数据走 full 模式
        if "__DATA_JSON_PLACEHOLDER__" in html:
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
            saved = save_sync_state(body)
            resp = json.dumps(
                {"ok": bool(saved), "updatedAt": (saved or {}).get("updatedAt")},
                ensure_ascii=False,
            ).encode("utf-8")
            self._send_json(resp)
        except Exception:
            self.send_response(500)
            self.end_headers()

    def _handle_remove_video(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0 or length > 1024:
                self.send_response(400)
                self.end_headers()
                return
            body = json.loads(self.rfile.read(length))
            code = (body.get("code") or "").upper()
            source = (body.get("source") or "missav").lower()
            if not code:
                self.send_response(400)
                self.end_headers()
                return

            data_file = DATA_FILES.get(source)
            removed = {}
            removed_file = ROOT / ".removed_videos.json"
            if removed_file.is_file():
                try:
                    removed = json.loads(removed_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            key = source + ":" + code
            removed[key] = time.time()
            removed_file.write_text(
                json.dumps(removed, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            if data_file and data_file.is_file():
                try:
                    data = json.loads(data_file.read_text(encoding="utf-8"))
                    before = len(data.get("videos", []))
                    data["videos"] = [
                        v
                        for v in data.get("videos", [])
                        if (v.get("code") or "").upper() != code
                    ]
                    if len(data.get("videos", [])) < before:
                        data_file.write_text(
                            json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        _rebuild_index()
                except Exception:
                    pass

            resp = json.dumps({"ok": True, "code": code, "source": source}).encode(
                "utf-8"
            )
            self._send_json(resp)
        except Exception:
            self.send_response(500)
            self.end_headers()

    def _handle_restore_video(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0 or length > 512 * 1024:
                self.send_response(400)
                self.end_headers()
                return
            body = json.loads(self.rfile.read(length))
            code = (body.get("code") or "").upper()
            source = (body.get("source") or "missav").lower()
            video = body.get("video") or {}
            if not code:
                self.send_response(400)
                self.end_headers()
                return

            removed_file = ROOT / ".removed_videos.json"
            removed = {}
            if removed_file.is_file():
                try:
                    removed = json.loads(removed_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            removed.pop(source + ":" + code, None)
            removed_file.write_text(
                json.dumps(removed, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            data_file = DATA_FILES.get(source)
            if data_file and data_file.is_file() and isinstance(video, dict):
                data = json.loads(data_file.read_text(encoding="utf-8"))
                videos = data.get("videos") or []
                exists = any((v.get("code") or "").upper() == code for v in videos)
                if not exists:
                    video["code"] = code
                    video["source"] = source
                    videos.append(video)
                    data["videos"] = videos
                    data_file.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    if source == "missav":
                        _rebuild_index()

            resp = json.dumps({"ok": True, "code": code, "source": source}).encode(
                "utf-8"
            )
            self._send_json(resp)
        except Exception:
            self.send_response(500)
            self.end_headers()

    def _handle_add_trending_videos(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0 or length > 512 * 1024:
                self.send_response(400)
                self.end_headers()
                return
            body = json.loads(self.rfile.read(length))
            source = (body.get("source") or "missav").lower()
            videos = body.get("videos") or []
            data_file = DATA_FILES.get(source)
            if (
                source not in ("missav", "jable")
                or not data_file
                or not isinstance(videos, list)
            ):
                self.send_response(400)
                self.end_headers()
                return
            data = (
                json.loads(data_file.read_text(encoding="utf-8"))
                if data_file.is_file()
                else {"videos": []}
            )
            stored = data.get("videos") or []
            existing_codes = {(video.get("code") or "").upper() for video in stored}
            added = 0
            for video in videos[:100]:
                if not isinstance(video, dict):
                    continue
                code = (video.get("code") or "").upper().strip()
                if not code or code in existing_codes:
                    continue
                stored.append(
                    {
                        "code": code,
                        "title": str(video.get("title") or ""),
                        "url": str(video.get("url") or ""),
                        "cover": str(video.get("cover") or ""),
                        "preview": str(video.get("preview") or ""),
                        "date": str(video.get("date") or ""),
                        "actresses": list(video.get("actresses") or []),
                        "is_multi": bool(video.get("is_multi")),
                        "tags": list(video.get("tags") or []),
                        "source": source,
                    }
                )
                existing_codes.add(code)
                added += 1
            data["videos"] = stored
            if added:
                data_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                if source == "missav":
                    _rebuild_index()
            self._send_json(
                json.dumps(
                    {
                        "ok": True,
                        "source": source,
                        "added": added,
                        "skipped": len(videos) - added,
                        "total": len(stored),
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
            )
        except Exception:
            self.send_response(500)
            self.end_headers()

    def _handle_save_jable_metadata(self):
        self._handle_save_trending_metadata("jable")

    def _handle_save_missav_metadata(self):
        self._handle_save_trending_metadata("missav")

    def _handle_save_trending_metadata(self, source):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0 or length > 128 * 1024:
                self.send_response(400)
                self.end_headers()
                return
            payload = json.loads(self.rfile.read(length))
            records = payload.get("videos") or []
            if not isinstance(records, list) or len(records) > 50:
                self.send_response(502)
                self.end_headers()
                return
            data_file = DATA_FILES[source]
            data = (
                json.loads(data_file.read_text(encoding="utf-8"))
                if data_file.is_file()
                else {"videos": []}
            )
            stored = {
                (video.get("code") or "").upper(): video
                for video in data.get("videos") or []
            }
            updated = []
            metadata = {}
            metadata_path = trending_metadata_path(source)
            if metadata_path.is_file():
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                except Exception:
                    metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            cached = []
            for record in records:
                if not isinstance(record, dict):
                    continue
                code = str(record.get("code") or "").upper().strip()
                if not code:
                    continue
                video = stored.get(code)
                title = str(record.get("title") or "").strip()
                original_title = str(record.get("original_title") or "").strip()
                actresses = [
                    str(value).strip()
                    for value in record.get("actresses") or []
                    if str(value).strip()
                ]
                tags = [
                    str(value).strip()
                    for value in record.get("tags") or []
                    if str(value).strip()
                ]
                entry = {
                    "title": title[:500],
                    "original_title": original_title[:500],
                    "actresses": actresses[:12],
                    "tags": tags[:20],
                    "is_multi": len(actresses) > 1,
                    "metadata_fetched_at": int(time.time() * 1000),
                }
                metadata[code] = entry
                cached.append(code)
                if not video:
                    continue
                if title:
                    video["title"] = title[:500]
                if original_title:
                    video["original_title"] = original_title[:500]
                if actresses:
                    video["actresses"] = actresses[:12]
                if tags:
                    video["tags"] = tags[:20]
                video["is_multi"] = len(video.get("actresses") or []) > 1
                video["metadata_fetched_at"] = int(time.time() * 1000)
                updated.append(code)
            if updated:
                data_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            if cached:
                metadata_path.write_text(
                    json.dumps(metadata, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            self._send_json(
                json.dumps(
                    {"ok": True, "updated": updated, "cached": cached},
                    ensure_ascii=False,
                ).encode("utf-8")
            )
        except Exception:
            self.send_response(500)
            self.end_headers()

    def _handle_favorite_media_cache(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = (
                json.loads(self.rfile.read(length)) if 0 < length <= 64 * 1024 else {}
            )
            source = re.sub(r"[^a-z0-9_-]", "", str(body.get("source") or "").lower())
            code = re.sub(r"[^a-z0-9_-]", "", str(body.get("code") or "").lower())
            action = body.get("action")
            if (
                source not in ("missav", "jable")
                or not code
                or action not in ("remove", "remove_temp", "prepare")
            ):
                self.send_response(400)
                self.end_headers()
                return
            if action == "prepare":
                threading.Thread(
                    target=_prepare_favorite_gif,
                    args=(source, code),
                    daemon=True,
                ).start()
                self._send_json(
                    json.dumps({"ok": True, "queued": True}).encode("utf-8")
                )
                return
            removed = 0
            directories = (
                [CACHE_DIR / "play_temp" / code]
                if action == "remove_temp"
                else [
                    FAVORITE_MEDIA_CACHE_DIR / source / code,
                    CACHE_DIR / "play" / code,
                ]
            )
            for directory in directories:
                if directory.exists():
                    removed += sum(1 for path in directory.rglob("*") if path.is_file())
                    shutil.rmtree(directory, ignore_errors=True)
            self._send_json(
                json.dumps({"ok": True, "removed": removed}).encode("utf-8")
            )
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

    def _send_bytes(self, data, content_type, cache_control, extra_headers=None):
        # cache_control 可以是数字(秒)或字符串(如 "no-cache", "max-age=3600")
        if isinstance(cache_control, int):
            cc_value = f"max-age={cache_control}"
        else:
            cc_value = cache_control
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cc_value)
        self.send_header("Access-Control-Allow-Origin", "*")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    @staticmethod
    def _http_date(epoch_seconds):
        from email.utils import formatdate

        return formatdate(epoch_seconds, usegmt=True)

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
        self.send_response(404)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(PLACEHOLDER_PNG)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(PLACEHOLDER_PNG)

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


class PickerHTTPServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = False


def run():
    from .config import CACHE_DIR, PORT, get_lan_ip

    CACHE_DIR.mkdir(exist_ok=True)
    ip = get_lan_ip()
    print(f"\n  AV Roulette Browser V2 (模块化)")
    print(f"  缓存目录: {CACHE_DIR}")
    print(f"  本机:  http://localhost:{PORT}")
    print(f"  手机:  http://{ip}:{PORT}")
    print(f"  状态:  http://localhost:{PORT}/stats")
    print(f"  缓存计划: http://localhost:{PORT}/cache_plan")
    print(f"  按 Ctrl+C 停止\n")
    print("  缓存预热: 已关闭（仅直接播放时缓存当前作品）")
    with PickerHTTPServer(("0.0.0.0", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  已停止")
