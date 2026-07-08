"""MissAV scraper — parses HTML and appends to picker_data.json.

Usage: python scrape_missav.py < saved.html
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DATA_FILE = ROOT / "picker_data.json"

CODE_RE = re.compile(r"/(?:dm\d+/)?cn/([a-z0-9]+(?:-[a-z0-9]+)*)", re.I)
COVER_RE = re.compile(r"https?://[a-z0-9.-]*fourhoi\.com/[^\"' ]+cover[^\"' ]*", re.I)


def parse(html):
    items, seen = [], set()
    for m in CODE_RE.finditer(html):
        code = m.group(1).upper()
        code = re.sub(r"-UNSENSORED.*", "", code, flags=re.I)
        code = re.sub(r"-CHINESE.*", "", code, flags=re.I)
        if code in seen or len(code) < 4 or code.endswith("COVER"):
            continue
        seen.add(code)
        start, end = max(0, m.start() - 600), min(len(html), m.end() + 600)
        local = html[start:end]
        cover_m = COVER_RE.search(local)
        cover = cover_m.group(0) if cover_m else ""
        title = ""
        dm = ""
        dm_m = re.search(r"/(dm\d+)/cn/", m.group(0), re.I)
        if dm_m:
            dm = dm_m.group(1)
        for tm in re.finditer(r'(?:alt|title)=["\']([^"\']{1,200})["\']', local, re.I):
            t = tm.group(1).strip()
            if t and t.upper() != code and "cover" not in t.lower():
                title = t
                break
        url = (
            f"https://missav.ws/{dm}/cn/{code.lower()}"
            if dm
            else f"https://missav.ws/cn/{code.lower()}"
        )
        items.append(
            {
                "code": code,
                "title": title,
                "cover": cover,
                "url": url,
                "source": "missav",
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
        print("WARNING: No videos found", file=sys.stderr)
        sys.exit(0)

    data = {"source": "missav", "videos": [], "actresses": []}
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
