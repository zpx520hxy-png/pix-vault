# -*- coding: utf-8 -*-
"""
并发爬取所有作品详情页,提取发布日期
- 数据源: result.json 里所有出现过的 code+url + multi_top30.json + 附录里的收藏番号
- 输出: scripts/missav_scrape/dates.json {code: "YYYY-MM-DD"}
- 并发 10 路, 已抓的跳过
"""
import json
import re
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).parent
COOKIE = (ROOT / "cookies.txt").read_text(encoding="utf-8").strip()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
DATES_PATH = ROOT / "dates.json"

dates = json.loads(DATES_PATH.read_text(encoding="utf-8")) if DATES_PATH.exists() else {}
print(f"已缓存 {len(dates)} 个日期")

# ---- 收集所有需要爬的 (code, url) ----
to_fetch = {}  # code -> url

# result.json
result = json.load(open(ROOT / "result.json", encoding="utf-8"))
for slug, info in result.items():
    for v in info.get("top10", []):
        if v["code"] not in dates:
            to_fetch[v["code"]] = v["url"]

# multi_top30.json
multi = json.load(open(ROOT / "multi_top30.json", encoding="utf-8"))
for v in multi:
    if v["code"] not in dates:
        to_fetch[v["code"]] = v["url"]

# 附录里的收藏番号(从 saved.json 拿 url)
try:
    saved = json.load(open(ROOT / "saved.json", encoding="utf-8"))
    for v in saved:
        if v["code"] not in dates and v["code"] not in to_fetch:
            to_fetch[v["code"]] = v["url"]
except Exception:
    pass

print(f"需要爬: {len(to_fetch)} 个")

DATE_RE = re.compile(r'<time datetime="(\d{4}-\d{2}-\d{2})')

def fetch_date(item):
    code, url = item
    cmd = [
        "curl", "-sSL", "--compressed",
        "-A", UA,
        "-H", f"Cookie: {COOKIE}",
        "-H", "Accept: text/html",
        "-H", "Accept-Language: zh-CN,zh;q=0.9",
        "-H", "Referer: https://missav.ai/",
        "--max-time", "25",
        url,
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30)
        if out.returncode != 0:
            return code, None
        m = DATE_RE.search(out.stdout)
        if m:
            return code, m.group(1)
        return code, ""  # 页面爬到但没日期
    except Exception as e:
        return code, None

# ---- 并发 ----
items = list(to_fetch.items())
done = 0
fail = 0
with ThreadPoolExecutor(max_workers=10) as pool:
    futures = {pool.submit(fetch_date, it): it[0] for it in items}
    for fut in as_completed(futures):
        code, date = fut.result()
        done += 1
        if date:
            dates[code] = date
        else:
            fail += 1
        if done % 30 == 0:
            print(f"  {done}/{len(items)}  ok={done-fail}  fail={fail}")
            DATES_PATH.write_text(json.dumps(dates, ensure_ascii=False, indent=2), encoding="utf-8")

DATES_PATH.write_text(json.dumps(dates, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n完成. total dates={len(dates)} fail={fail}")
