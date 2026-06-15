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
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

# ── 配置 ──────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

PORT = int(os.environ.get("PIXVAULT_PORT", "8720"))
ROOT = Path(os.environ.get("PIXVAULT_IMAGES", BASE_DIR.parent / "generated_images"))
PID_FILE = BASE_DIR / ".pix-vault.pid"

# ── 标签提取 ──────────────────────────────────────────────

# 只能从 batch log 提取的标签
BATCH_LOG_TAGS = {"大胸", "NSFW"}

# 内容标签关键词
TAG_KEYWORDS = {
    "大胸": ["large breasts", "huge breasts", "big breasts", "busty",
             "voluptuous", "giant breasts", "massive breasts", "heavy breasts"],
    "NSFW": ["nsfw", "explicit", "nude", "naked", "pussy", "cock", "penis",
             "breasts", "nipple", "bare pussy", "bare breasts", "spread legs",
             "cum", "creampie", "sex", "fuck", "penetration", "masturbat",
             "dildo", "vibrator", "bondage", "fetish", "bdsm", "orgy", "threesome"],
}

# 文件名 → 内容标签（写实/动漫走文件夹，不从文件名猜）
FILENAME_TAGS = {
    "大胸": ["busty", "bigbreast", "largebreast", "hugebreast"],
    "欧美": ["european", "caucasian", "western", "american",
             "blonde", "freckle", "redhead", "ginger", "sunkissed", "tanned"],
    "东亚": ["asian", "japanese", "chinese", "korean", "eastasian",
             "porcelain", "hime", "kimono", "cheongsam", "qipao", "pale skin"],
}

# 文件夹 → 风格标签（唯一权威来源）
# NSFW: 文件夹名含 nsfw/sex/nude/noobai 的默认标 NSFW
FOLDER_TAGS = {
    "pony_nsfw_1000":    ["动漫", "大胸", "NSFW"],
    "pony_nsfw_1000_v2": ["动漫", "大胸", "NSFW"],
    "pony_nsfw_1000_v3": ["动漫", "大胸", "NSFW"],
    "noobai_1000":       ["动漫", "大胸", "NSFW"],
    "sex_animagine":     ["动漫", "NSFW"],
    "sex_pony":          ["动漫", "NSFW"],
    "real_100":          ["写实"],
    "sexy_100":          ["写实"],
    "sexy_100_nude":     ["写实", "NSFW"],
    "lingerie_50":       ["写实"],
    "stability":         ["写实"],
    "siliconflow":       ["写实"],
    "comfyui":           ["写实"],
    "gpt_generate":      ["写实"],
    "model_test":        [],
    "quick_nsfw":        ["NSFW"],
    "qq_bot_avatar":     [],
}


def parse_batch_logs(root: Path) -> dict[str, set[str]]:
    """解析 _batch_log.txt，只提取 BATCH_LOG_TAGS 中的标签"""
    folder_tags: dict[str, set[str]] = {}

    for log_path in sorted(root.rglob("_batch_log.txt")):
        folder = log_path.parent.name
        tags = set()
        try:
            text = log_path.read_text(encoding="utf-8", errors="ignore").lower()
        except Exception:
            continue

        for tag in BATCH_LOG_TAGS:
            for kw in TAG_KEYWORDS.get(tag, []):
                if kw in text:
                    tags.add(tag)
                    break
        if tags:
            folder_tags[folder] = tags

    return folder_tags


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
            img["tags"] = img["tags"] + ["正常"]
            normal_count += 1
    if normal_count > 0:
        tag_counts["正常"] = normal_count
    # 排序：正常紧挨 NSFW 后面
    priority = {"NSFW": 0, "正常": 1}
    sorted_tags = sorted(tag_counts.keys(), key=lambda t: (priority.get(t, 99), -tag_counts[t]))
    return tag_counts, sorted_tags


def scan_images(root: Path) -> list[dict]:
    """扫描图片并打标签"""
    batch_tags = parse_batch_logs(root)

    images = []
    for f in sorted(root.rglob("*")):
        if f.suffix.lower() not in IMG_EXTS:
            continue
        rel = f.relative_to(root)
        parts = rel.parts
        if parts[0] == "favorites":
            continue
        cat = parts[0] if len(parts) > 1 else "(root)"

        # 1. 文件夹默认标签 + batch log 补充
        tags = set(FOLDER_TAGS.get(cat, []))
        if cat in batch_tags:
            tags.update(batch_tags[cat])

        # 2. 文件名关键词检测
        name_lower = f.name.lower()
        for tag, keywords in FILENAME_TAGS.items():
            for kw in keywords:
                if kw in name_lower:
                    tags.add(tag)
                    break

        images.append({
            "path": str(rel).replace("\\", "/"),
            "category": cat,
            "name": f.name,
            "size": f.stat().st_size,
            "tags": sorted(tags),
        })
    return images


# ── HTTP Handler ──────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    images: list[dict] = []
    tag_counts: dict[str, int] = {}
    all_tags: list[str] = []

    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filepath: Path):
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
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                self.wfile.write(chunk)

    def _filter_images(self, params: dict) -> list[dict]:
        """根据 cats / tags / fav 参数过滤"""
        pool = self.images

        # 收藏夹模式：只返回 favorites 文件夹的图片
        if params.get("fav", [None])[0] == "1":
            fav_dir = ROOT / "favorites"
            favs = []
            if fav_dir.is_dir():
                for f in sorted(fav_dir.rglob("*")):
                    if f.suffix.lower() in IMG_EXTS:
                        favs.append({
                            "path": "favorites/" + str(f.relative_to(fav_dir)).replace("\\", "/"),
                            "category": "favorites",
                            "name": f.name,
                            "size": f.stat().st_size,
                            "tags": [],
                        })
            return favs

        # 分类过滤
        cats_param = params.get("cats", [None])[0]
        if cats_param:
            cats_filter = set(cats_param.split(","))
            pool = [img for img in pool if img["category"] in cats_filter]

        # 标签过滤
        tags_param = params.get("tags", [None])[0]
        if tags_param:
            tags_filter = set(tags_param.split(","))
            pool = [img for img in pool if tags_filter.issubset(set(img.get("tags", [])))]

        return pool

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/api/rescan":
            Handler.images = scan_images(ROOT)
            Handler.tag_counts, Handler.all_tags = build_tag_index(Handler.images)
            self._send_json({
                "ok": True,
                "total": len(Handler.images),
                "tags": Handler.all_tags,
            })

        elif path == "/api/cats":
            cat_counts = {}
            for img in self.images:
                cat_counts[img["category"]] = cat_counts.get(img["category"], 0) + 1
            # 统计收藏夹图片数
            fav_dir = ROOT / "favorites"
            fav_count = 0
            if fav_dir.is_dir():
                fav_count = sum(1 for f in fav_dir.rglob("*") if f.suffix.lower() in IMG_EXTS)
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
            self._send_json(random.choice(pool))

        elif path == "/api/random_batch":
            n = min(int(params.get("n", ["20"])[0]), 200)
            pool = self._filter_images(params)
            sample = random.sample(pool, min(n, len(pool)))
            random.shuffle(sample)
            self._send_json(sample)

        # 顺序模式下获取全量排序列表（只返回元数据）
        elif path == "/api/all":
            pool = self._filter_images(params)
            # 按路径排序
            pool.sort(key=lambda x: x["path"])
            self._send_json(pool)

        elif path == "/api/dislikes":
            dl_path = ROOT / ".disliked.json"
            disliked = []
            if dl_path.is_file():
                disliked = json.loads(dl_path.read_text("utf-8"))
            self._send_json({"paths": disliked, "count": len(disliked)})

        elif path == "/api/favorites":
            fav_dir = ROOT / "favorites"
            favs = []
            if fav_dir.is_dir():
                for f in sorted(fav_dir.rglob("*")):
                    if f.suffix.lower() in IMG_EXTS:
                        favs.append({
                            "path": "favorites/" + str(f.relative_to(fav_dir)).replace("\\", "/"),
                            "name": f.name,
                            "size": f.stat().st_size,
                            "category": "favorites",
                            "tags": [],
                        })
            self._send_json({"images": favs, "count": len(favs)})

        elif path.startswith("/img/"):
            rel = unquote(path[len("/img/"):])
            filepath = (ROOT / rel).resolve()
            if not str(filepath).startswith(str(ROOT.resolve())):
                self.send_error(403)
                return
            self._send_file(filepath)

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
