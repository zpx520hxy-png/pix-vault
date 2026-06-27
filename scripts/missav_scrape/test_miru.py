import subprocess, re, time
from pathlib import Path

ROOT = Path('D:/360MoveData/Users/Pda/Desktop/claude/scripts/missav_scrape')
cookie = (ROOT / 'cookies.txt').read_text(encoding='utf-8').strip()
ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'
HARD = {'OFJE','IDBD','MIRD','PFES','WAVR','AVOPVR','IPVR','SIVR','JUSD','PRMJ'}
MULTI_KW = ['COLLECTION','全明星','BEST','感谢会','合集','精选','Bako','Party','盛会','双打','史上最强',
            '12小时','16小时','48小时','8小时盒装','梦幻共演','联合主演','20周年','VVVIP']

def is_multi(num, title):
    if num.split('-')[0] in HARD: return True
    for kw in MULTI_KW:
        if kw in title: return True
    return False

url = 'https://missav.ai/dm80/cn/actresses/miru?sort=views'
solo = []
for page in range(1, 10):
    page_url = url if page == 1 else f'{url}&page={page}'
    out = subprocess.run(['curl', '-sSL', '--compressed', '-A', ua, '-H', f'Cookie: {cookie}',
        '-H', 'Accept-Language: zh-CN,zh;q=0.9', '--max-time', '20', page_url],
        capture_output=True, text=True, encoding='utf-8', timeout=25)
    html = out.stdout
    vids = re.findall(
        r'<div class="my-2 text-sm text-nord4 truncate">\s*<a\s+href="([^"]+)"[^>]*>\s*(.*?)\s*</a>',
        html, re.DOTALL
    )
    solo_this = 0
    for vurl, title in vids:
        t = re.sub(r'\s+', ' ', title.strip())
        cm = re.match(r'([A-Z0-9]+-\d+)', t)
        code = cm.group(1) if cm else '?'
        multi = is_multi(code, t)
        if not multi:
            solo.append(code)
            solo_this += 1
    print(f'  page {page}: {len(vids)} videos, {solo_this} solo, total_solo={len(solo)}')
    if len(solo) >= 15 or len(vids) < 8:
        break
    time.sleep(0.4)

print(f'Final: {len(solo)} solo for miru')
for c in solo[:15]:
    print(f'  {c}')
