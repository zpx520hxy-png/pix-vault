"""
MissAV 收藏抓取（用 curl，绕开 Cloudflare 对 httpx 的 JA3 拦截）
"""
from __future__ import annotations
import re
import time
import html
import json
import subprocess
from pathlib import Path
import urllib.parse as up

ROOT = Path(__file__).parent
COOKIE = (ROOT / "cookies.txt").read_text(encoding="utf-8").strip()
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
BASE = "https://missav.ws"
CACHE = ROOT / "cache"
CACHE.mkdir(exist_ok=True)


def cache_path(url: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", url.replace("https://", ""))
    return CACHE / f"{safe[:200]}.html"


def get(url: str, *, force: bool = False, sleep: float = 1.0) -> str:
    p = cache_path(url)
    if p.exists() and not force:
        return p.read_text(encoding="utf-8")
    print(f"  GET {url}", flush=True)
    cmd = [
        "curl", "-sSL", "--compressed",
        "-A", UA,
        "-H", f"Cookie: {COOKIE}",
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
        "-H", "Referer: https://missav.ai/",
        "--max-time", "30",
        url,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise RuntimeError(f"curl failed: {out.stderr[:300]}")
    text = out.stdout
    if "Just a moment" in text or "Cloudflare" in text and len(text) < 10000:
        raise RuntimeError(f"hit Cloudflare on {url}")
    p.write_text(text, encoding="utf-8")
    time.sleep(sleep)
    return text


# ---- parsing ---------------------------------------------------------------

VIDEO_CARD_RE = re.compile(
    r'<div class="my-2 text-sm text-nord4 truncate">\s*<a[^>]*?href="([^"]+)"[^>]*>\s*([^<]+)\s*</a>',
    re.DOTALL,
)


def parse_video_list(text: str) -> list[dict]:
    out, seen = [], set()
    for m in VIDEO_CARD_RE.finditer(text):
        url = m.group(1)
        title = html.unescape(re.sub(r"\s+", " ", m.group(2).strip()))
        cm = re.match(r"([A-Z0-9]+-\d+)\s*(.*)", title)
        code = cm.group(1) if cm else None
        if not code or code in seen:
            continue
        seen.add(code)
        out.append({"url": url, "code": code, "title": title})
    return out


def parse_video_actresses(text: str) -> list[dict]:
    """
    在视频详情页里只取真正的"女優:"段落里的链接。
    格式: <span>女優:</span> ... <a href="...actresses/<slug>" ...>名字</a>
    多位女优会有多个 <div class="text-secondary"> ... </div> 块，但同一个 span:女優 区块内可能并列。
    """
    actresses, seen = [], set()
    # 找到所有 "女優:" 后面紧跟着的 actresses 链接
    # 用单行 dotall 范围限定，从 "女優:" 到下一个 "<span>" 或 "</div>"
    sections = re.findall(
        r'<span>(?:女優|女优|Actress(?:es)?|Actrices|演員)[\s:：]*</span>(.*?)</div>',
        text,
        re.DOTALL,
    )
    for sec in sections:
        for m in re.finditer(
            r'<a[^>]+href="([^"]*actresses/([^"#?/]+))"[^>]*>\s*([^<]+?)\s*</a>',
            sec,
            re.DOTALL,
        ):
            url, slug, name = m.group(1), up.unquote(m.group(2)), m.group(3).strip()
            name = html.unescape(re.sub(r"\s+", " ", name))
            if not name or slug in seen or slug in {"ranking", "popular", "list"}:
                continue
            if not url.startswith("http"):
                url = up.urljoin(BASE, url)
            seen.add(slug)
            actresses.append({"slug": slug, "name": name, "url": url})
    return actresses


# ---- pipeline -------------------------------------------------------------

def scrape_saved() -> list[dict]:
    saved = []
    for page in range(1, 20):  # 最多到 20，看翻到没数据为止
        url = f"{BASE}/cn/saved?page={page}" if page > 1 else f"{BASE}/cn/saved"
        text = get(url)
        items = parse_video_list(text)
        print(f"  page {page}: {len(items)} videos")
        if not items:
            break
        saved.extend(items)
        # 检查是否有下一页
        if f"cn/saved?page={page+1}" not in text:
            print(f"  no page {page+1}, stop")
            break
    uniq = {s["code"]: s for s in saved}
    return list(uniq.values())


def collect_actresses(saved: list[dict]) -> dict:
    actress_map: dict[str, dict] = {}
    for i, v in enumerate(saved, 1):
        print(f"[{i}/{len(saved)}] {v['code']}")
        try:
            text = get(v["url"])
        except Exception as e:
            print(f"  !! {e}")
            continue
        for a in parse_video_actresses(text):
            slug = a["slug"]
            if slug not in actress_map:
                actress_map[slug] = {**a, "from_videos": []}
            actress_map[slug]["from_videos"].append(v["code"])
    return actress_map


def normalize_actress_url(url: str) -> str:
    # 统一走 cn 路径拿简体中文标题
    url = re.sub(r"missav\.ai/(?:[a-z]{2,3}/)?actresses/", "missav.ai/cn/actresses/", url)
    # 详情页链接也统一成 /cn/
    return url


def fetch_actress_top(url: str, top_n: int = 10) -> list[dict]:
    sorted_url = url + ("?" if "?" not in url else "&") + "sort=views"
    try:
        text = get(sorted_url)
    except Exception as e:
        print(f"  !! sort failed: {e}; fallback")
        text = get(url)
    return parse_video_list(text)[:top_n]


def main():
    print("=== 1) saved 页 ===")
    saved = scrape_saved()
    print(f"总收藏 {len(saved)} 部")
    (ROOT / "saved.json").write_text(
        json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== 2) 详情页 → 女优 ===")
    actress_map = collect_actresses(saved)
    # 按出现频次排序（被收藏视频里出现次数最多的女优在前）
    actress_map = dict(
        sorted(actress_map.items(), key=lambda kv: -len(kv[1]["from_videos"]))
    )
    print(f"共 {len(actress_map)} 位女优")
    (ROOT / "actresses.json").write_text(
        json.dumps(actress_map, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== 3) 每位女优 top 10 ===")
    result = {}
    for i, (slug, info) in enumerate(actress_map.items(), 1):
        url = normalize_actress_url(info["url"])
        print(f"[{i}/{len(actress_map)}] {info['name']} ({slug})")
        try:
            top = fetch_actress_top(url, 10)
        except Exception as e:
            print(f"  !! {e}")
            top = []
        result[slug] = {**info, "url": url, "top10": top}

    (ROOT / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✓ 写入 result.json")


if __name__ == "__main__":
    main()
