# -*- coding: utf-8 -*-
"""
重新爬每个女优主页,取 Top 15(原本只爬到 Top 10)
直接读取 result.json 里已有的 url(已含 dm 前缀,不会重定向)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scrape import get, parse_video_list

ROOT = Path(__file__).parent
result_path = ROOT / "result.json"
result = json.load(open(result_path, encoding="utf-8"))

TOP_N = 15

def fetch_top(url, top_n=TOP_N):
    base = url + ("?" if "?" not in url else "&") + "sort=views"
    out, seen = [], set()
    for page in range(1, 4):
        page_url = base if page == 1 else f"{base}&page={page}"
        try:
            text = get(page_url, sleep=0.4)
        except Exception as e:
            if page == 1:
                raise
            print(f"  !! page {page} failed: {e}; stop paging")
            break
        items = parse_video_list(text)
        for v in items:
            if v["code"] not in seen:
                seen.add(v["code"])
                out.append(v)
        if len(out) >= top_n:
            break
        if len(items) < 12:
            # 这一页没满 12 个,说明已经到尾了
            break
    return out[:top_n]

print(f"Refetching {len(result)} actresses, top {TOP_N} each...")
fail = []
for i, (slug, info) in enumerate(result.items(), 1):
    name = info["name"]
    url = info["url"]
    print(f"[{i:3}/{len(result)}] {name[:30]}")
    try:
        top = fetch_top(url)
        if len(top) < 5:
            print(f"  !! only {len(top)} videos parsed; will retry")
            fail.append(slug)
            continue
        info["top10"] = top  # 沿用旧字段名,避免改下游
        print(f"  -> {len(top)} videos")
    except Exception as e:
        print(f"  !! ERROR: {e}")
        fail.append(slug)

result_path.write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(f"\nDone. failures: {len(fail)}")
if fail:
    for s in fail:
        print(f"  {s}")
