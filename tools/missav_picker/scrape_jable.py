"""Jable scraper — parses one page of HTML from stdin and appends to jable_data.json.

Usage (run via AI assistant, one page at a time):
  1. AI fetches page HTML via Chrome network_request
  2. AI pipes HTML to: python scrape_jable.py
  3. Repeat for pages 1..63 (24 per page, ~1512 total)

The script accumulates results across runs and deduplicates by code.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DATA_FILE = ROOT / "jable_data.json"

CODE_RE = re.compile(r"/videos/([a-z0-9]+(?:-[a-z0-9]+)*)/?", re.I)
COVER_RE = re.compile(
    r'(?:data-original|data-src|src)=\\?["\'](https?://assets-cdn\.jable\.tv/[^"\'\\ ]+320x180[^"\'\\ ]*\.(?:jpe?g|png|webp))',
    re.I,
)
TITLE_RE = re.compile(r"<h[4]\b[^>]*>([^<]{5,200})</h[4]>", re.I)
CODE_PREFIX_RE = re.compile(r"^([A-Z0-9]{2,8}(?:-[A-Z0-9]{2,8})?)\b", re.I)
ALT_RE = re.compile(r'alt=\\?"([^"\\]{5,200})\\?"', re.I)


def parse(html):
    items, seen = [], set()
    for m in CODE_RE.finditer(html):
        code = m.group(1).upper()
        if code in seen:
            continue
        seen.add(code)
        start, end = max(0, m.start() - 2000), min(len(html), m.end() + 600)
        local = html[start:end]
        cover_m = COVER_RE.search(local)
        cover = cover_m.group(1) if cover_m else ""
        title = ""
        for tm in TITLE_RE.finditer(local):
            t = tm.group(1).strip()
            cm = CODE_PREFIX_RE.match(t)
            if cm and cm.group(1).upper() == code:
                title = t
                break
        if not title:
            alt_m = ALT_RE.search(local)
            if alt_m:
                title = alt_m.group(1).strip()
        items.append(
            {
                "code": code,
                "title": title,
                "cover": cover,
                "url": f"https://jable.tv/videos/{code.lower()}/",
                "source": "jable",
                "is_multi": False,
            }
        )
    return items


def main():
    html = sys.stdin.read()
    if not html or len(html) < 1000:
        print("ERROR: No valid HTML input", file=sys.stderr)
        sys.exit(1)

    items = parse(html)
    if not items:
        print("WARNING: No videos found in HTML", file=sys.stderr)
        sys.exit(0)

    data = {"source": "jable", "videos": [], "actresses": []}
    if DATA_FILE.is_file():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    existing = {v.get("code", "").upper() for v in data.get("videos", [])}
    new = 0
    for item in items:
        if item["code"] not in existing:
            existing.add(item["code"])
            data["videos"].append(item)
            new += 1

    tmp = DATA_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DATA_FILE)

    print(
        json.dumps({"page_items": len(items), "new": new, "total": len(data["videos"])})
    )


if __name__ == "__main__":
    main()
