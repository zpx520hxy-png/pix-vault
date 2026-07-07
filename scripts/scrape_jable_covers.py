# -*- coding: utf-8 -*-
"""从 Jable 视频页抓 og:image 封面 URL,存到 jable_covers.json。

输入: tools/missav_picker/jable_data.json  (含 videos[*].url / videos[*].code)
输出: tools/missav_picker/jable_covers.json (code 大写 -> cover URL)

特性:
- stdlib only (urllib + re)
- 已有 cover URL 且是真实截图模式 (assets-cdn.jable.tv/.../videos_screenshots/.../preview.jpg) → 跳过抓取
- 限速 0.3s/请求, 失败重试 2 次 (退避 1s, 3s)
- 每 20 部打印进度, 末尾输出成功/失败统计
- 增量更新: 已有的 jable_covers.json 不会被覆盖, 只补缺失的

用法:
    python scripts/scrape_jable_covers.py            # 增量抓所有缺 cover 的
    python scripts/scrape_jable_covers.py --force   # 全部重抓
    python scripts/scrape_jable_covers.py --limit 5 # 只抓前 5 部 (调试)
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

JABLE_DATA = Path('D:/360MoveData/Users/Pda/Desktop/claude/tools/missav_picker/jable_data.json')
JABLE_COVERS = Path('D:/360MoveData/Users/Pda/Desktop/claude/tools/missav_picker/jable_covers.json')

# 已确认的"真实截图"URL 模式: assets-cdn.jable.tv/.../videos_screenshots/<dir>/<id>/preview.jpg
# 命中则认为是有效 cover, 跳过重抓
REAL_SCREENSHOT_RE = re.compile(
    r'^https?://assets-cdn\.jable\.tv/contents/videos_screenshots/\d+/\d+/preview\.jpg$'
)

# 从 HTML 抓 og:image / twitter:image / <link rel="preload" as="image" href="...">
OG_IMAGE_RE = re.compile(
    r'''(?ix)
    <meta\s+[^>]*property=["']og:image["']\s+[^>]*content=["']([^"']+)["']
    |<meta\s+[^>]*content=["']([^"']+)["'][^>]*property=["']og:image["']
    |<meta\s+[^>]*name=["']twitter:image["']\s+[^>]*content=["']([^"']+)["']
    |<meta\s+[^>]*content=["']([^"']+)["'][^>]*name=["']twitter:image["']
    |<link\s+[^>]*rel=["']preload["'][^>]*as=["']image["'][^>]*href=["']([^"']+)["']
    |<link\s+[^>]*href=["']([^"']+)["'][^>]*rel=["']preload["'][^>]*as=["']image["']
    '''
)

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)


def _http_get(url, timeout=15):
    """GET 请求, 返回 (status, body_bytes)。"""
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept-Language': 'en-US,en;q=0.9'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, None


def _extract_cover(html):
    """从 HTML 里提取 og:image / twitter:image / preload image,返回第一个匹配。"""
    if not html:
        return None
    m = OG_IMAGE_RE.search(html)
    if not m:
        return None
    # 6 个组里只有一个非空
    for g in m.groups():
        if g:
            return g.strip()
    return None


def _code_to_url(code):
    """'SSIS-834' -> 'https://jable.tv/videos/ssis-834/'"""
    return f'https://jable.tv/videos/{code.lower()}/'


def _scrape_one(code, retries=2):
    """抓单个 code 的 cover, 返回 URL 或 None。"""
    url = _code_to_url(code)
    backoff = [1, 3]
    for attempt in range(retries + 1):
        status, body = _http_get(url)
        if status == 200 and body:
            cover = _extract_cover(body.decode('utf-8', errors='ignore'))
            if cover:
                return cover
        # 失败: 退避后重试
        if attempt < retries:
            time.sleep(backoff[min(attempt, len(backoff) - 1)])
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true', help='重抓所有,忽略 jable_covers.json 已有的值')
    parser.add_argument('--limit', type=int, default=0, help='只抓前 N 部 (调试用)')
    parser.add_argument('--delay', type=float, default=0.3, help='请求间隔秒数')
    args = parser.parse_args()

    if not JABLE_DATA.exists():
        sys.exit(f'[ERROR] 缺数据: {JABLE_DATA} (先跑 scripts/build_jable_data.py)')

    with open(JABLE_DATA, encoding='utf-8') as f:
        data = json.load(f)
    videos = data.get('videos', [])

    # 加载已有 covers
    covers = {}
    if JABLE_COVERS.exists() and not args.force:
        try:
            with open(JABLE_COVERS, encoding='utf-8') as f:
                covers = json.load(f)
            print(f'[INFO] 已加载 {len(covers)} 条已有 cover')
        except json.JSONDecodeError:
            print(f'[WARN] {JABLE_COVERS} 损坏, 当空文件处理')

    # 决定要抓的 code 列表
    todo = []
    for v in videos:
        code = v.get('code')
        if not code:
            continue
        existing = covers.get(code, '')
        if not args.force and existing and REAL_SCREENSHOT_RE.match(existing):
            continue  # 已有真实截图,跳过
        todo.append(code)

    if args.limit:
        todo = todo[:args.limit]

    print(f'[INFO] 待抓: {len(todo)} 部 / 总: {len(videos)} 部')

    ok = fail = 0
    failures = []
    for i, code in enumerate(todo, 1):
        cover = _scrape_one(code)
        if cover:
            covers[code] = cover
            ok += 1
        else:
            fail += 1
            failures.append(code)
        if i % 20 == 0 or i == len(todo):
            print(f'  [{i}/{len(todo)}] ok={ok} fail={fail}')
        time.sleep(args.delay)

    # 落盘
    JABLE_COVERS.parent.mkdir(parents=True, exist_ok=True)
    with open(JABLE_COVERS, 'w', encoding='utf-8') as f:
        json.dump(covers, f, ensure_ascii=False, indent=2)

    print(f'[OK] {JABLE_COVERS}  ({len(covers)} 条, 本次 +{ok} 成功 / {fail} 失败)')
    if failures:
        sample = ', '.join(failures[:10])
        print(f'[FAIL] 共 {fail} 部失败, 样例: {sample}')


if __name__ == '__main__':
    main()
