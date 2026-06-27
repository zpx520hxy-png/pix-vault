# -*- coding: utf-8 -*-
"""
重新爬每个女优页,翻页直到凑够 15 部单人作品.
写入 result_solo15.json (覆盖原 top10 字段)
"""
import json, re, subprocess, time
from pathlib import Path
from collections import defaultdict

ROOT = Path('D:/360MoveData/Users/Pda/Desktop/claude/scripts/missav_scrape')
RESULT = ROOT / 'result.json'
COOKIE = (ROOT / 'cookies.txt').read_text(encoding='utf-8').strip()
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'

# ---- 多人判定(同其他脚本) ----
HARD_MULTI_PREFIX = {'OFJE', 'IDBD', 'MIRD', 'PFES', 'WAVR', 'AVOPVR', 'IPVR', 'SIVR'}
MULTI_KEYWORDS = [
    '全明星', '全部 7 个标题', 'COLLECTION', 'GIRLS COLLECTION',
    '粉丝感', '感恩节', '感谢会', '感謝', '巴士之旅', 'BAKO', 'Bako', 'Bakobako',
    '狂欢', '大乱交', '超级大乱交', '大狂欢', '群交', 'Orgy', 'ORGY',
    'PARTY', 'Party', '盛大聚会', '盛会', '大聚会', '24场', '23 人', '23人',
    '双打', '史上最强', 'VVVIP', 'SUPER VVVIP', '完整最佳版', '完整 48 小时',
    '8 小时', '8小时盒装', '12小时', '12 小时', '16 小时', '16小时', '48 小时',
    '梦幻共演', '联合主演', '超级罕见的联合', '哈林岛特辑', '20周年',
]
MULTI_QTY_RE = re.compile(
    r'\d{2,4}\s*位|\d{2,4}\s*人(?!性|妻|夫)|\d{2,4}\s*名身穿|\d{2,4}\s*名.{0,3}女|\d{2,4}\s*部作品|\d{3,}\s*张|\d{2,3}\s*个场景'
)
def is_multi(num, title):
    if num.split('-')[0] in HARD_MULTI_PREFIX: return True
    if any(kw in title for kw in MULTI_KEYWORDS): return True
    return bool(MULTI_QTY_RE.search(title))

# ---- curl ----
CACHE = ROOT / 'cache'
CACHE.mkdir(exist_ok=True)
def get(url):
    safe = re.sub(r'[^a-zA-Z0-9._-]', '_', url.replace('https://', ''))[:200]
    p = CACHE / f'{safe}.html'
    if p.exists(): return p.read_text(encoding='utf-8')
    cmd = ['curl', '-sSL', '--compressed', '-A', UA, '-H', f'Cookie: {COOKIE}',
           '-H', 'Accept: text/html', '-H', 'Accept-Language: zh-CN,zh;q=0.9',
           '-H', 'Referer: https://missav.ai/', '--max-time', '25', url]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=30)
    if out.returncode != 0: raise RuntimeError(f'curl fail: {out.stderr[:100]}')
    if len(out.stdout) < 2000: raise RuntimeError(f'short page {len(out.stdout)}')
    p.write_text(out.stdout, encoding='utf-8')
    time.sleep(0.3)
    return out.stdout

VIDEO_RE = re.compile(
    r'<div class="my-2 text-sm text-nord4 truncate">\s*<a[^>]*?href="([^"]+)"[^>]*>\s*([^<]+)\s*</a>', re.DOTALL
)

def parse_videos(html):
    seen, out = set(), []
    for m in VIDEO_RE.finditer(html):
        url, raw = m.group(1), m.group(2).strip()
        code_m = re.match(r'([A-Z0-9]+-\d+)', raw)
        if not code_m: continue
        code = code_m.group(1)
        # Extract slug from URL for cover
        slug_m = re.search(r'/cn/([^/?]+?)(?:\?|$)', url)
        slug = slug_m.group(1) if slug_m else code.lower()
        title = re.sub(r'\s+', ' ', raw).strip()
        if code in seen: continue
        seen.add(code)
        out.append({'code': code, 'title': title, 'url': url, 'slug': slug})
    return out

# ---- 主流程 ----
result = json.load(open(RESULT, encoding='utf-8'))
print(f'Actresses to process: {len(result)}')

failures = []
for i, (slug, info) in enumerate(result.items(), 1):
    name = info['name']
    base_url = info['url']
    print(f'[{i:3}/{len(result)}] {name[:25]}', end=' ', flush=True)

    solo15 = []
    try:
        # 第一轮: sort=views 翻页直到凑够 15 或超过 5 页
        for sort_mode in ('sort=views', 'sort=date'):
            if len(solo15) >= 15:
                break
            base = base_url + ('&' if '?' in base_url else '?') + sort_mode
            for page in range(1, 6):
                page_url = base if page == 1 else f'{base}&page={page}'
                try:
                    html = get(page_url)
                except Exception:
                    break  # 这页超时/404,跳过
                videos = parse_videos(html)
                for v in videos:
                    if not is_multi(v['code'], v['title']):
                        # 去重(views/date 可能重复)
                        if v['code'] not in {x['code'] for x in solo15}:
                            solo15.append(v)
                if len(solo15) >= 15 or len(videos) < 8:
                    break
        print(f'-> {len(solo15)} solo')
    except Exception as e:
        print(f'!! {e}')
        failures.append((slug, name))

    info['top10'] = solo15[:15]  # 复用字段名

# Save
out_path = ROOT / 'result_solo15.json'
out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'\nDone. Failures: {len(failures)}')
for s, n in failures: print(f'  {n}')
