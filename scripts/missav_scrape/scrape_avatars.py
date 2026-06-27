# -*- coding: utf-8 -*-
"""从 missav 女优列表页提取 name→actor_id 映射,头像 URL: fourhoi.com/actress/{id}-t.jpg"""
import subprocess, re, time, json
from pathlib import Path

ROOT = Path('D:/360MoveData/Users/Pda/Desktop/claude/scripts/missav_scrape')
COOKIE = (ROOT / 'cookies.txt').read_text(encoding='utf-8').strip()
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'

# 爬类型: missav.ws 的 actresses 列表
# Pattern from our test: <img src="https://fourhoi.com/actress/{id}-t.jpg" ... > 附近有名字
# 需要同时抓名字和 ID

# Approach: 先爬 missav.ai 每个女优页提取四hoi actress ID
# 因为已有的 result.json 里有每个女优的 URL

result = json.load(open(ROOT / 'result.json', encoding='utf-8'))
# 加载已有
actress_map = {}
av_file = ROOT / 'actress_avatars.json'
if av_file.exists():
    actress_map = json.load(open(av_file, encoding='utf-8'))
    print(f'Loaded {len(actress_map)} existing IDs')

print(f'Scraping {len(result)} actress pages for avatar IDs...')
for i, (slug, info) in enumerate(result.items(), 1):
    name = info['name']
    if name in actress_map:
        continue
    url = info['url']  # e.g. https://missav.ai/dm80/cn/actresses/miru
    try:
        out = subprocess.run(['curl', '-sSL', '--compressed', '-A', UA, '-H', f'Cookie: {COOKIE}',
            '-H', 'Accept-Language: zh-CN,zh;q=0.9', '--max-time', '15', url],
            capture_output=True, text=True, encoding='utf-8', timeout=20)
        html = out.stdout
        # Find actress ID pattern: fourhoi.com/actress/{id}-t.jpg OR /actress/{id}
        m = re.search(r'fourhoi\.com/actress/(\d+)(?:-t)?\.(?:jpg|jpeg|png)', html)
        if not m:
            m = re.search(r'/actress/(\d+)[\"\'/]', html)
        if m:
            actress_map[name] = m.group(1)
            print(f'[{i:3}/{len(result)}] {name[:25]} -> id={m.group(1)}')
        else:
            # Try scraping the actress listing page with the slug
            act_slug = slug if slug else ''
            list_url = f'https://missav.ai/dm80/cn/actresses/{act_slug}'
            out2 = subprocess.run(['curl', '-sSL', '--compressed', '-A', UA, '-H', f'Cookie: {COOKIE}',
                '-H', 'Accept-Language: zh-CN,zh;q=0.9', '--max-time', '15', list_url],
                capture_output=True, text=True, encoding='utf-8', timeout=20)
            html2 = out2.stdout
            m2 = re.search(r'fourhoi\.com/actress/(\d+)(?:-t)?\.(?:jpg|jpeg|png)', html2)
            if not m2:
                m2 = re.search(r'/actress/(\d+)[\"\'/]', html2)
            if m2:
                actress_map[name] = m2.group(1)
                print(f'[{i:3}/{len(result)}] {name[:25]} -> id={m2.group(1)} (retry)')
            else:
                print(f'[{i:3}/{len(result)}] {name[:25]} -- no avatar found')
    except Exception as e:
        print(f'[{i:3}/{len(result)}] {name[:25]} !! {e}')
    time.sleep(0.25)

# Save
out_path = ROOT / 'actress_avatars.json'
out_path.write_text(json.dumps(actress_map, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'\nSaved {len(actress_map)} avatar IDs to {out_path}')
