import subprocess, re, time
from pathlib import Path
ROOT = Path('D:/360MoveData/Users/Pda/Desktop/claude/scripts/missav_scrape')
cookie = (ROOT / 'cookies.txt').read_text(encoding='utf-8').strip()
ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36'
HARD = {'OFJE','IDBD','MIRD','PFES','WAVR','AVOPVR','IPVR','SIVR','JUSD','PRMJ'}
def is_hard(num): return num.split('-')[0] in HARD

PAT_VID = re.compile(r'<div class="my-2 text-sm text-nord4 truncate">\s*<a[^>]*?href="([^"]+)"[^>]*>\s*([^<]+)\s*</a>', re.DOTALL)

solo = []
for page in range(1, 6):
    url = f'https://missav.ai/dm80/cn/actresses/miru?sort=date'
    if page > 1: url += f'&page={page}'
    out = subprocess.run(['curl','-sSL','--compressed','-A',ua,'-H',f'Cookie: {cookie}',
        '-H','Accept-Language: zh-CN,zh;q=0.9','--max-time','20',url],
        capture_output=True, text=True, encoding='utf-8', timeout=25)
    vids = PAT_VID.findall(out.stdout)
    s = 0
    for vurl, title in vids:
        t = re.sub(r'\s+',' ',title.strip())
        cm = re.match(r'([A-Z0-9]+-\d+)', t)
        if cm and not is_hard(cm.group(1)):
            solo.append(cm.group(1))
            s += 1
    print(f'page {page}: {len(vids)} videos, {s} solo (total={len(solo)})')
    if len(solo) >= 15 or len(vids) < 8: break
    time.sleep(0.3)
print(f'\nResult: {len(solo)} solo for miru')
for c in solo: print(f'  {c}')
