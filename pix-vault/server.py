#!/usr/bin/env python3
"""PixVault — 本地图片画廊浏览器

浏览、筛选、收藏、标记不喜欢、幻灯片播放、顺序/随机模式。

配置（环境变量）：
  PIXVAULT_PORT     — 端口（默认 8720）
  PIXVAULT_IMAGES   — 图片根目录（默认 ../generated_images）
"""

import json
import os
import random
import re
import shutil
import gzip
import hashlib
import mimetypes
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ── 配置 ──────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

PORT = int(os.environ.get("PIXVAULT_PORT", "8720"))
ROOT = Path(os.environ.get("PIXVAULT_IMAGES", BASE_DIR.parent / "generated_images"))
PID_FILE = BASE_DIR / ".pix-vault.pid"
THUMB_DIR = BASE_DIR / ".thumbs"
THUMB_MAX_WIDTH = 480
THUMB_QUALITY = 78
# 缩略图生成锁 — 避免并发请求同一张图重复生成
_thumb_locks: dict[str, threading.Lock] = {}
_thumb_locks_master = threading.Lock()

# 过滤池缓存 — key=(cats_param, tags_param, scan_revision)
# 同筛选条件下 Q 键连点不会反复 O(N) 过滤；scan_revision 变化时旧条目自然不命中
_filter_cache: dict[tuple[str, str, int], list[dict]] = {}
_filter_cache_lock = threading.Lock()
_FILTER_CACHE_MAX = 32

# ── 标签提取 ──────────────────────────────────────────────

# 新标签系统：从文件名直接解析中文元数据
# 文件命名: 画风_人数_分级_身材_构图_模型_编号.png
# 例: 写实_单人_NSFW_巨乳_半身_realvis_mix_0020.png
# 旧文件: pony_0740.png, pn1k_0252.png → 从文件夹推断

# 文件名标签 → 直接映射
FILENAME_TAG_MAP = {
    "写实": "写实", "动漫": "动漫",
    "NSFW": "NSFW",
    # 注意：不含「正常」— 文件夹分类是权威来源，「正常」由 build_tag_index 自动给无 NSFW 的图补
    "单人": "单人", "双人": "双人", "多人": "多人",
    "巨乳": "巨乳", "贫乳": "贫乳",
    "特写": "特写", "半身": "半身", "全身": "全身",
    "POV": "POV", "背光": "背光", "低角度": "低角度",
    "pony": "pony", "realvis": "realvis", "noobai": "noobai", "animagine": "animagine",
}

# 文件夹 → 默认标签（仅用于无文件名标签的旧图片）
FOLDER_DEFAULTS = {
    "pony_nsfw_1000":    ["动漫", "NSFW", "巨乳", "pony"],
    "pony_nsfw_1000_v2": ["动漫", "NSFW", "巨乳", "pony"],
    "pony_nsfw_1000_v3": ["动漫", "NSFW", "巨乳", "pony"],
    "noobai_1000":       ["动漫", "NSFW", "巨乳", "noobai"],
    "sex_animagine":     ["动漫", "NSFW", "animagine"],
    "sex_pony":          ["动漫", "NSFW", "pony"],
    "real_100":          ["写实", "realvis"],
    "sexy_100":          ["写实", "realvis"],
    "sexy_100_nude":     ["写实", "NSFW", "realvis"],
    "lingerie_50":       ["写实", "realvis"],
    "stability":         ["写实", "stability"],
    "siliconflow":       ["写实"],
    "comfyui":           ["写实"],
    "gpt_generate":      ["写实"],
    "quick_nsfw":        ["NSFW"],
    "mixed_1000":        [],
    "model_test":        [],
    "qq_bot_avatar":     [],
}

# 上层标签优先级（画风/分级/人数/身材 排前面）
TAG_ORDER = {"NSFW":0,"正常":1,"写实":2,"动漫":3,"单人":4,"双人":5,"多人":6,"巨乳":7,"贫乳":8}


def parse_filename_tags(name: str) -> set[str]:
    """从文件名解析标签，例如 '写实_单人_NSFW_巨乳_半身_realvis_mix_0020.png'"""
    stem = name.rsplit(".", 1)[0]
    tags = set()
    for part in stem.split("_"):
        if part in FILENAME_TAG_MAP:
            tags.add(FILENAME_TAG_MAP[part])
    return tags


def build_tag_index(images: list[dict]) -> tuple[dict[str, int], list[str]]:
    """统计标签覆盖 + 自动生成「正常」标签（无 NSFW 的图）"""
    tag_counts: dict[str, int] = {}
    for img in images:
        for t in img.get("tags", []):
            tag_counts[t] = tag_counts.get(t, 0) + 1
    # 「正常」= 不含 NSFW 的图片
    normal_count = 0
    for img in images:
        if "NSFW" not in img.get("tags", []):
            img["tags"].append("正常")
            normal_count += 1
    if normal_count > 0:
        tag_counts["正常"] = normal_count
    sorted_tags = sorted(tag_counts.keys(), key=lambda t: (TAG_ORDER.get(t, 99), -tag_counts[t]))
    return tag_counts, sorted_tags


def scan_images(root: Path) -> list[dict]:
    """扫描图片并打标签：文件名优先 → 文件夹默认 → 「正常」自动补

    用 os.scandir 递归 — 在 Windows 上 entry.stat() 复用 WIN32_FIND_DATA，
    不会再发 stat 系统调用，比 Path.rglob('*') + f.stat() 快 5-10×。
    """
    images: list[dict] = []
    root_str = str(root)

    def walk(dir_path: str, cat: str | None):
        try:
            it = os.scandir(dir_path)
        except OSError:
            return
        with it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    # 顶层 favorites 文件夹跳过（不进 pool）
                    if cat is None and entry.name == "favorites":
                        continue
                    # 顶层目录名就是分类，子层级保留首层分类
                    walk(entry.path, entry.name if cat is None else cat)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                ext = os.path.splitext(entry.name)[1].lower()
                if ext not in IMG_EXTS:
                    continue

                cat_name = cat if cat else "(root)"
                folder_defs = FOLDER_DEFAULTS.get(cat_name, [])
                filename_tags = parse_filename_tags(entry.name)

                # 基线：始终先合并文件夹默认标签（含 NSFW 等语义信息）
                # 文件夹分类是权威来源，文件名标签是补充
                tags = set(folder_defs)
                tags.update(filename_tags)
                # 注意：不做「正常」↔「NSFW」互斥 — build_tag_index 会自动给无 NSFW 的图补「正常」

                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0

                # 相对路径 — 避免构造 Path 对象
                abs_path = entry.path
                rel = abs_path[len(root_str):].lstrip("\\/")
                rel_str = rel.replace("\\", "/")

                images.append({
                    "path": rel_str,
                    "category": cat_name,
                    "name": entry.name,
                    "size": size,
                    "tags": sorted(tags),
                })

    walk(root_str, None)
    images.sort(key=lambda x: x["path"])
    return images


def list_favorites(fav_dir: Path) -> list[dict]:
    """列出收藏夹下所有图片（scandir 递归）"""
    favs: list[dict] = []
    if not fav_dir.is_dir():
        return favs
    fav_str = str(fav_dir)

    def walk(dir_path: str):
        try:
            it = os.scandir(dir_path)
        except OSError:
            return
        with it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    walk(entry.path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                ext = os.path.splitext(entry.name)[1].lower()
                if ext not in IMG_EXTS:
                    continue
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                rel = entry.path[len(fav_str):].lstrip("\\/").replace("\\", "/")
                favs.append({
                    "path": "favorites/" + rel,
                    "category": "favorites",
                    "name": entry.name,
                    "size": size,
                    "tags": [],
                })

    walk(fav_str)
    favs.sort(key=lambda x: x["path"])
    return favs


# ── 缩略图 ────────────────────────────────────────────────

def _thumb_lock_for(rel: str) -> threading.Lock:
    """每张图一个锁，避免并发请求重复生成。"""
    with _thumb_locks_master:
        lk = _thumb_locks.get(rel)
        if lk is None:
            lk = threading.Lock()
            _thumb_locks[rel] = lk
        return lk


def get_thumb_path(rel: str, src: Path) -> Path | None:
    """返回缩略图路径，按需生成。生成失败返回 None（调用方 fallback 到原图）。

    缩略图存到 .thumbs/<原相对路径>.jpg，按源图 mtime 失效。
    """
    if not HAS_PIL:
        return None

    thumb_path = THUMB_DIR / (rel + ".jpg")
    try:
        src_mtime = src.stat().st_mtime
    except OSError:
        return None

    # 命中：缩略图存在且不旧于源图
    if thumb_path.is_file():
        try:
            if thumb_path.stat().st_mtime >= src_mtime:
                return thumb_path
        except OSError:
            pass

    # 生成（同图加锁）
    lock = _thumb_lock_for(rel)
    with lock:
        # 双重检查（拿到锁后另一个线程可能已经生成完）
        if thumb_path.is_file():
            try:
                if thumb_path.stat().st_mtime >= src_mtime:
                    return thumb_path
            except OSError:
                pass

        try:
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(src) as im:
                # 透明通道压平到白底（jpeg 不支持透明）
                if im.mode in ("RGBA", "LA", "P"):
                    im = im.convert("RGBA")
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
                    im = bg
                elif im.mode != "RGB":
                    im = im.convert("RGB")
                im.thumbnail((THUMB_MAX_WIDTH, THUMB_MAX_WIDTH * 4), Image.Resampling.LANCZOS)
                # 临时文件 + 原子替换，避免半截缩略图
                tmp = thumb_path.with_suffix(".jpg.tmp")
                im.save(tmp, "JPEG", quality=THUMB_QUALITY, optimize=True, progressive=True)
                os.replace(tmp, thumb_path)
        except Exception as e:
            print(f"thumb fail {rel}: {e}")
            return None

    return thumb_path


# ── HTTP Handler ──────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    images: list[dict] = []
    tag_counts: dict[str, int] = {}
    all_tags: list[str] = []
    scan_revision: int = 0  # 每次 scan_images 后 +1，用作 ETag/缓存 key 的版本号

    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200, etag=None, allow_gzip=False):
        # ETag 命中 → 304 短路，不需要序列化
        if etag:
            inm = self.headers.get("If-None-Match", "")
            if inm == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.end_headers()
                return

        body = json.dumps(data, ensure_ascii=False).encode("utf-8")

        encoding = None
        if allow_gzip and len(body) > 1024:
            ae = self.headers.get("Accept-Encoding", "")
            if "gzip" in ae:
                body = gzip.compress(body, compresslevel=6)
                encoding = "gzip"

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        if encoding:
            self.send_header("Content-Encoding", encoding)
            self.send_header("Vary", "Accept-Encoding")
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filepath: Path, immutable: bool = False):
        if not filepath.is_file():
            self.send_error(404)
            return
        mime, _ = mimetypes.guess_type(str(filepath))
        if not mime:
            mime = "application/octet-stream"
        size = filepath.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", size)
        if immutable:
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                self.wfile.write(chunk)

    def _filter_images(self, params: dict) -> list[dict]:
        """根据 cats / tags / fav 参数过滤，结果按 (cats, tags, scan_revision) 缓存"""
        # 收藏夹模式：每次都即时列举（文件可能变化，不缓存）
        if params.get("fav", [None])[0] == "1":
            return list_favorites(ROOT / "favorites")

        cats_param = params.get("cats", [None])[0] or ""
        tags_param = params.get("tags", [None])[0] or ""
        rev = Handler.scan_revision
        key = (cats_param, tags_param, rev)

        with _filter_cache_lock:
            cached = _filter_cache.get(key)
            if cached is not None:
                return cached

        pool = Handler.images
        if cats_param:
            cats_filter = set(cats_param.split(","))
            pool = [img for img in pool if img["category"] in cats_filter]
        if tags_param:
            tags_filter = set(tags_param.split(","))
            pool = [img for img in pool if tags_filter.issubset(set(img.get("tags", [])))]

        with _filter_cache_lock:
            # 简单 LRU：超出上限就清空（同一会话筛选条件本来也不会很多）
            if len(_filter_cache) >= _FILTER_CACHE_MAX:
                _filter_cache.clear()
            _filter_cache[key] = pool

        return pool

    def do_GET(self):
        # 修复中文: Python http.server 用 Latin-1 解码路径
        # self.path 里的字节被错误当成 Latin-1 字符, 还原为原始字节再解码
        try:
            raw_bytes = self.path.encode("latin-1")
            raw_path = raw_bytes.decode("utf-8")
        except (UnicodeError, LookupError):
            raw_path = self.path
        parsed = urlparse(raw_path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/api/rescan":
            Handler.images = scan_images(ROOT)
            Handler.tag_counts, Handler.all_tags = build_tag_index(Handler.images)
            Handler.scan_revision += 1
            self._send_json({
                "ok": True,
                "total": len(Handler.images),
                "tags": Handler.all_tags,
            })

        elif path == "/api/count":
            pool = self._filter_images(params)
            self._send_json({"count": len(pool)})

        elif path == "/api/cats":
            cat_counts = {}
            for img in self.images:
                cat_counts[img["category"]] = cat_counts.get(img["category"], 0) + 1
            # 统计收藏夹图片数（用 scandir，避免 rglob 列举非图片文件）
            fav_count = len(list_favorites(ROOT / "favorites"))
            self._send_json({
                "total": len(self.images),
                "categories": [
                    {"name": k, "count": v}
                    for k, v in sorted(cat_counts.items())
                ],
                "tags": Handler.all_tags,
                "tagCounts": Handler.tag_counts,
                "favCount": fav_count,
            })

        elif path == "/api/random":
            pool = self._filter_images(params)
            if not pool:
                self._send_json(None)
                return
            exclude_param = params.get("exclude", [None])[0]
            if exclude_param:
                exclude_set = set(exclude_param.split(","))
                # 即时拒抽：先随机抽 10 次试试不在 exclude 中
                # exclude 一般 ≤ 200，pool 几千张时随机命中率很高
                for _ in range(10):
                    cand = random.choice(pool)
                    if cand["path"] not in exclude_set:
                        self._send_json(cand)
                        return
                # 10 次都被排除 → 退化为全量过滤再抽（少见情况，例如池子小或大半已浏览）
                filtered = [img for img in pool if img["path"] not in exclude_set]
                self._send_json(random.choice(filtered) if filtered else None)
                return
            self._send_json(random.choice(pool))

        elif path == "/api/random_batch":
            n = min(int(params.get("n", ["20"])[0]), 200)
            pool = self._filter_images(params)
            sample = random.sample(pool, min(n, len(pool)))
            random.shuffle(sample)
            self._send_json(sample)

        # 顺序模式下获取全量排序列表（只返回元数据）
        elif path == "/api/all":
            # _filter_images 返回的池子已按 path 排序（scan_images 末尾 sort + filter 保留顺序）
            pool = self._filter_images(params)
            # ETag 基于扫描版本号 + 查询参数（cats/tags/fav）— 只要扫描没变、筛选条件没变就 304
            etag_key = f"{Handler.scan_revision}|{parsed.query}".encode()
            etag = '"' + hashlib.md5(etag_key).hexdigest()[:16] + '"'
            self._send_json(pool, etag=etag, allow_gzip=True)

        elif path == "/api/dislikes":
            dl_path = ROOT / ".disliked.json"
            disliked = []
            if dl_path.is_file():
                disliked = json.loads(dl_path.read_text("utf-8"))
            self._send_json({"paths": disliked, "count": len(disliked)})

        elif path == "/api/favorites":
            favs = list_favorites(ROOT / "favorites")
            self._send_json({"images": favs, "count": len(favs)})

        elif path.startswith("/img/"):
            rel = unquote(path[len("/img/"):])
            filepath = (ROOT / rel).resolve()
            if not str(filepath).startswith(str(ROOT.resolve())):
                self.send_error(403)
                return
            self._send_file(filepath)

        elif path.startswith("/thumb/"):
            rel = unquote(path[len("/thumb/"):])
            src = (ROOT / rel).resolve()
            if not str(src).startswith(str(ROOT.resolve())) or not src.is_file():
                self.send_error(404)
                return
            # 小图（< 80 KB）/ gif / 不支持 PIL — 直接返回原图
            try:
                src_size = src.stat().st_size
            except OSError:
                self.send_error(404)
                return
            if src_size < 80 * 1024 or src.suffix.lower() == ".gif" or not HAS_PIL:
                self._send_file(src)
                return
            thumb = get_thumb_path(rel, src)
            if thumb and thumb.is_file():
                self._send_file(thumb, immutable=True)
            else:
                # 生成失败 fallback 原图
                self._send_file(src)

        elif path.startswith("/static/"):
            rel = unquote(path[len("/static/"):])
            safe = Path(rel).as_posix()
            filepath = (STATIC_DIR / safe).resolve()
            if not str(filepath).startswith(str(STATIC_DIR.resolve())):
                self.send_error(403)
                return
            self._send_file(filepath)

        elif path == "/" or path == "/index.html":
            self._serve_html()

        elif path == "/m" or path == "/mobile":
            self._serve_mobile()

        else:
            self.send_error(404)

    def _serve_html(self):
        content = (STATIC_DIR / "index.html").read_text("utf-8")
        html = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def _serve_mobile(self):
        content = (STATIC_DIR / "mobile.html").read_text("utf-8")
        html = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if path == "/api/favorite":
            img_path = body.get("path", "")
            if not img_path:
                self._send_json({"ok": False, "error": "missing path"}, 400)
                return
            src = (ROOT / img_path).resolve()
            if not str(src).startswith(str(ROOT.resolve())) or not src.is_file():
                self._send_json({"ok": False, "error": "invalid path"}, 400)
                return
            fav_dir = ROOT / "favorites"
            fav_dir.mkdir(parents=True, exist_ok=True)
            dst = fav_dir / src.name
            if dst.exists():
                stem, ext = dst.stem, dst.suffix
                i = 1
                while dst.exists():
                    dst = fav_dir / f"{stem}_({i}){ext}"
                    i += 1
            shutil.copy2(src, dst)
            self._send_json({"ok": True, "action": "added", "dest": str(dst.relative_to(ROOT)).replace("\\", "/")})

        elif path == "/api/unfavorite":
            fname = body.get("name", "")
            if not fname:
                self._send_json({"ok": False, "error": "missing name"}, 400)
                return
            fav_dir = ROOT / "favorites"
            target = (fav_dir / fname).resolve()
            if not str(target).startswith(str(fav_dir.resolve())) or not target.is_file():
                self._send_json({"ok": False, "error": "file not in favorites"}, 400)
                return
            target.unlink()
            self._send_json({"ok": True, "action": "removed"})

        elif path == "/api/dislike":
            img_path = body.get("path", "")
            if not img_path:
                self._send_json({"ok": False, "error": "missing path"}, 400)
                return
            # 存到 .disliked.json 列表
            dl_path = ROOT / ".disliked.json"
            disliked = []
            if dl_path.is_file():
                disliked = json.loads(dl_path.read_text("utf-8"))
            if img_path not in disliked:
                disliked.append(img_path)
                dl_path.write_text(json.dumps(disliked, ensure_ascii=False, indent=2), "utf-8")
            self._send_json({"ok": True, "action": "added", "count": len(disliked)})

        elif path == "/api/undislike":
            img_path = body.get("path", "")
            if not img_path:
                self._send_json({"ok": False, "error": "missing path"}, 400)
                return
            dl_path = ROOT / ".disliked.json"
            disliked = []
            if dl_path.is_file():
                disliked = json.loads(dl_path.read_text("utf-8"))
            if img_path in disliked:
                disliked.remove(img_path)
                dl_path.write_text(json.dumps(disliked, ensure_ascii=False, indent=2), "utf-8")
            self._send_json({"ok": True, "action": "removed", "count": len(disliked)})

        elif path == "/api/clear_dislikes":
            dl_path = ROOT / ".disliked.json"
            dl_path.write_text("[]", "utf-8")
            self._send_json({"ok": True})

        elif path == "/api/delete_disliked":
            dl_path = ROOT / ".disliked.json"
            if not dl_path.is_file():
                self._send_json({"ok": True, "deleted": 0})
                return
            disliked = json.loads(dl_path.read_text("utf-8"))
            deleted = 0
            for rel in disliked:
                src = (ROOT / rel).resolve()
                if str(src).startswith(str(ROOT.resolve())) and src.is_file():
                    src.unlink()
                    deleted += 1
            dl_path.write_text("[]", "utf-8")
            # 重新扫描
            Handler.images = scan_images(ROOT)
            Handler.tag_counts, Handler.all_tags = build_tag_index(Handler.images)
            Handler.scan_revision += 1
            self._send_json({"ok": True, "deleted": deleted, "total": len(Handler.images)})

        else:
            self.send_error(404)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器，支持并发请求"""
    daemon_threads = True  # 主线程退出时自动清理


# ── 主入口 ───────────────────────────────────────────────

def main():
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # 写 PID 文件
    PID_FILE.write_text(str(os.getpid()))

    print(f"Scanning {ROOT} ...")
    Handler.images = scan_images(ROOT)
    Handler.tag_counts, Handler.all_tags = build_tag_index(Handler.images)
    Handler.scan_revision += 1
    print(f"   Found {len(Handler.images)} images, {len(Handler.all_tags)} tags: {Handler.all_tags}")

    server = ThreadedHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"\n  Image Browser => http://localhost:{PORT}")
    print(f"  Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
