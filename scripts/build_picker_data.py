# -*- coding: utf-8 -*-
"""
构建 missav_picker 的统一作品库 JSON (拆两版)
- picker_data.json: 完整数据 (videos + actresses + ...)
- picker_index.json: 轻量索引 (actresses + display + avatars + groups + tags, 不含 videos)
"""
import json, re, urllib.parse as up
from pathlib import Path
from collections import Counter

ROOT = Path('D:/360MoveData/Users/Pda/Desktop/claude')
RESULT_SOLO15 = ROOT / 'scripts/missav_scrape/result_solo15.json'
RESULT = ROOT / 'scripts/missav_scrape/result.json'
MULTI = ROOT / 'scripts/missav_scrape/multi_top30.json'
DATES = ROOT / 'scripts/missav_scrape/dates.json'
SAVED = ROOT / 'scripts/missav_scrape/saved.json'
ACTOR_AVATAR_FILE = ROOT / 'scripts/missav_scrape/actress_avatars.json'
OUT = ROOT / 'tools/missav_picker/picker_data.json'
OUT_IDX = ROOT / 'tools/missav_picker/picker_index.json'

# ---- 多人判定 ----
# 合集系列前缀(全部标为多人/合集; 不含普通剧情系列)
COMPILE_PREFIX = {
    'OFJE', 'IDBD', 'MIRD', 'PFES', 'WAVR', 'AVOPVR', 'IPVR', 'SIVR',
    'MIZD', 'MKCK', 'PPBD', 'BMW', 'PBD', 'JUSD', 'RBB', 'NACX',
    'KSBJ', 'DAZD',
}
MULTI_KEYWORDS = [
    '全明星', '全部 7 个标题', 'COLLECTION', 'GIRLS COLLECTION',
    '粉丝感', '感恩节', '感谢会', '感謝', '巴士之旅', 'BAKO', 'Bako', 'Bakobako',
    '狂欢', '大乱交', '超级大乱交', '大狂欢', '群交', 'Orgy', 'ORGY',
    'PARTY', 'Party', '盛大聚会', '盛会', '大聚会', '24场', '23 人', '23人',
    '双打', '史上最强', 'VVVIP', 'SUPER VVVIP', '完整最佳版', '完整 48 小时',
    '8 小时', '8小时盒装', '12小时', '12 小时', '16 小时', '16小时', '48 小时',
    '梦幻共演', '联合主演', '超级罕见的联合', '哈林岛特辑', '20周年',
    'BEST', '名场面', '集锦', '精选',
    '永久保存版', '总集编',
]
MULTI_QTY_RE = re.compile(
    r'\d{3,}\s*(?:连发|连射|连続|弹幕|連発|連続)'
    r'|\d{2,4}\s*(?:位顶级|位女|位S级|位美|名身穿|名顶级|名AV|名S级|名美女|名女优|名女星|位AV)'
    r'|\d{2,4}\s*部作品'
    r'|\d{3,}\s*张(?:海报|照片|封面|海量)'
    r'|\d{2,3}\s*人(?:盛大|狂欢|聚会|大乱交|大混战|の大)'
    r'|全\d{2,3}\s*(?:名|位|人)'
)
def is_multi(num, title):
    prefix = num.split('-')[0]
    if prefix in COMPILE_PREFIX: return True
    if any(kw in title for kw in MULTI_KEYWORDS): return True
    return bool(MULTI_QTY_RE.search(title))

# ---- 标签提取 ----
TAGS = [
    ('巨乳',     ['巨乳', '大胸', '丰满', 'L罩杯', 'J罩杯', 'K罩杯', 'I罩杯', 'M罩杯', '美乳', '爆乳']),
    ('贫乳',     ['贫乳', '小胸', 'A罩杯', 'B罩杯']),
    ('美腿',     ['美腿', '黑丝', '丝袜', '裤袜']),
    ('NTR',      ['NTR', '寝取', '出轨', '通奸', '不忠', '戴绿帽', '偷情', '偷腥']),
    ('制服',     ['制服', '校服', '女学生', '校园']),
    ('OL',       ['OL', '上司', '同事', '办公室', '女白领', '女上司', '女老板', '女员工', '秘书']),
    ('老师',     ['老师', '女教师', '教师']),
    ('女仆',     ['女仆']),
    ('熟女',     ['人妻', '已婚', '熟女', '阿姨', '继母', '嫂子', '继妹', '老婆']),
    ('处女',     ['处女', '初体验', '首次性']),
    ('出道',     ['出道', '首秀', '首次亮相', '钻石新人', 'NO.1 STYLE', 'デビュー']),
    ('中出',     ['中出', '内射', '射精到', '内出', '阴道射精', 'CreamPie', 'Cream Pie']),
    ('颜射',     ['颜射', '射脸', '射一脸']),
    ('口交',     ['口交', '吹箫', '深喉']),
    ('女上位',   ['女上位', '骑乘', '女牛仔']),
    ('后入',     ['后入', '背入', '从后面']),
    ('潮吹',     ['潮吹', '喷水', '失禁', '尿尿', '男潮', '潮水']),
    ('高潮',     ['高潮', '阵发', '抽搐', '痉挛', '翘曲', '卡明']),
    ('调教',     ['调教', '驯服', 'SM', '束缚', '凌辱', '受虐', '虐待']),
    ('春药',     ['春药', '催情', '壮阳', '迷药']),
    ('多人',     ['3P', '4P', '群交', '乱交', '多P', '双打']),
    ('百合',     ['蕾丝']),
    ('BEST',     ['BEST', 'Best', '合集', '精选', '名场面', '集锦']),
    ('温泉',     ['温泉', '泡汤']),
    ('出差',     ['出差', '商务旅行']),
    ('女神',     ['女神', '美女', '女主角', '偶像']),
    ('辣妹',     ['辣妹', '黑辣妹']),
    ('妹妹',     ['妹妹', '青梅竹马', '闺蜜']),
    ('女高',     ['女高', '高中生']),
    ('乳交',     ['乳交', '乳沟']),
    ('强奸',     ['强奸', '强暴', '强行', '猥亵']),
    ('胖次',     ['胖次', '丁字裤']),
    ('未亡人',   ['寡妇', '未亡人']),
]

# ---- 加载 ----
if RESULT_SOLO15.exists():
    result = json.load(open(RESULT_SOLO15, encoding='utf-8'))
else:
    result = json.load(open(RESULT, encoding='utf-8'))
multi = json.load(open(MULTI, encoding='utf-8'))
dates = json.load(open(DATES, encoding='utf-8')) if DATES.exists() else {}
saved = json.load(open(SAVED, encoding='utf-8')) if SAVED.exists() else []

# ---- 女优名字去重 ----
_KANA = {
    'あ':'a','い':'i','う':'u','え':'e','お':'o','か':'ka','き':'ki','く':'ku','け':'ke','こ':'ko',
    'さ':'sa','し':'shi','す':'su','せ':'se','そ':'so','た':'ta','ち':'chi','つ':'tsu','て':'te','と':'to',
    'な':'na','に':'ni','ぬ':'nu','ね':'ne','の':'no','は':'ha','ひ':'hi','ふ':'fu','へ':'he','ほ':'ho',
    'ま':'ma','み':'mi','む':'mu','め':'me','も':'mo','や':'ya','ゆ':'yu','よ':'yo',
    'ら':'ra','り':'ri','る':'ru','れ':'re','ろ':'ro','わ':'wa','を':'wo','ん':'n',
    'が':'ga','ぎ':'gi','ぐ':'gu','げ':'ge','ご':'go','ざ':'za','じ':'ji','ず':'zu','ぜ':'ze','ぞ':'zo',
    'だ':'da','ぢ':'ji','づ':'zu','で':'de','ど':'do','ば':'ba','び':'bi','ぶ':'bu','べ':'be','ぼ':'bo',
    'ぱ':'pa','ぴ':'pi','ぷ':'pu','ぺ':'pe','ぽ':'po','ゃ':'ya','ゅ':'yu','ょ':'yo','っ':'',
    'ア':'a','イ':'i','ウ':'u','エ':'e','オ':'o','カ':'ka','キ':'ki','ク':'ku','ケ':'ke','コ':'ko',
    'サ':'sa','シ':'shi','ス':'su','セ':'se','ソ':'so','タ':'ta','チ':'chi','ツ':'tsu','テ':'te','ト':'to',
    'ナ':'na','ニ':'ni','ヌ':'nu','ネ':'ne','ノ':'no','ハ':'ha','ヒ':'hi','フ':'fu','ヘ':'he','ホ':'ho',
    'マ':'ma','ミ':'mi','ム':'mu','メ':'me','モ':'mo','ヤ':'ya','ユ':'yu','ヨ':'yo',
    'ラ':'ra','リ':'ri','ル':'ru','レ':'re','ロ':'ro','ワ':'wa','ヲ':'wo','ン':'n',
    'ガ':'ga','ギ':'gi','グ':'gu','ゲ':'ge','ゴ':'go','ザ':'za','ジ':'ji','ズ':'zu','ゼ':'ze','ゾ':'zo',
    'ダ':'da','ヂ':'ji','ヅ':'zu','デ':'de','ド':'do','バ':'ba','ビ':'bi','ブ':'bu','ベ':'be','ボ':'bo',
    'パ':'pa','ピ':'pi','プ':'pu','ペ':'pe','ポ':'po','ャ':'ya','ュ':'yu','ョ':'yo','ッ':'','ー':'-',
}
def kana_to_romaji(text):
    r, i = [], 0
    while i < len(text):
        ch = text[i]; key2 = ch + (text[i+1] if i+1 < len(text) else '')
        if key2 in _KANA: r.append(_KANA[key2]); i += 2
        elif ch in _KANA: v = _KANA[ch]; (v and r.append(v)); i += 1
        else: r.append(ch); i += 1
    return ''.join(r)

def build_display_name(name):
    if re.search(r'[぀-ゟ゠-ヿ]', name):
        clean = re.sub(r'[（(][^)）]*[)）]', '', name)
        romaji = re.sub(r'-+$', '', kana_to_romaji(clean)).strip()
        if romaji and romaji != name: return name + '  [' + romaji + ']'
    return name

# ---- 名字集 ----
actress_names_raw = set()
for slug, info in result.items():
    name = info['name']
    actress_names_raw.add(name)
    for part in re.split(r'[（）()\s]+', name):
        if len(part) >= 2 and re.search(r'[一-鿿぀-ゟ゠-ヿ]', part):
            actress_names_raw.add(part)
for v in multi:
    for a in v.get('actresses', []):
        actress_names_raw.add(a)
        for part in re.split(r'[（）()\s]+', a):
            if len(part) >= 2 and re.search(r'[一-鿿぀-ゟ゠-ヿ]', part):
                actress_names_raw.add(part)
ACTOR_NAMES_SORTED = sorted(actress_names_raw, key=len, reverse=True)

# 同人不同名去重 (canonical → [aliases])
ACTOR_ALIASES = {
    '新有菜 (桥本有菜) (新ありな (橋本ありな))': ['桥本有菜 (新有菜)'],
}
ACTOR_CANON = {}  # alias → canonical
for canon, aliases in ACTOR_ALIASES.items():
    for a in aliases:
        ACTOR_CANON[a] = canon

def canon_name(name):
    return ACTOR_CANON.get(name, name)

def strip_actress_names(title):
    clean = title
    for name in ACTOR_NAMES_SORTED: clean = clean.replace(name, '')
    return clean

def extract_tags(title):
    clean = strip_actress_names(title)
    tags = []
    for tag, keywords in TAGS:
        for kw in keywords:
            if kw in clean: tags.append(tag); break
    return tags

# ---- 构建作品库 ----
videos = {}
actress_index = {}

for slug, info in result.items():
    name = info['name']
    for v in info.get('top10', []):
        code = v['code']
        title_clean = v['title'].replace(code, '').strip()
        url = v['url']
        slug_m = re.search(r'/cn/([^/?]+?)(?:\?|$)', url)
        cover_slug = slug_m.group(1) if slug_m else code.lower()
        if code not in videos:
            videos[code] = {
                'code': code, 'title': title_clean,
                'url': url,
                'cover': f'https://fourhoi.com/{cover_slug}/cover-t.jpg',
                'preview': f'https://fourhoi.com/{cover_slug}/preview.mp4',
                'date': dates.get(code, ''),
                'is_multi': is_multi(code, title_clean),
                'tags': extract_tags(title_clean),
                'is_saved': False,
            }
            actress_index[code] = set()
        actress_index[code].add(canon_name(name))

for v in multi:
    code = v['code']
    if code not in videos:
        cs = v['slug']
        videos[code] = {
            'code': code, 'title': v['title'],
            'url': v['url'],
            'cover': f'https://fourhoi.com/{cs}/cover-t.jpg',
            'preview': f'https://fourhoi.com/{cs}/preview.mp4',
            'date': dates.get(code, ''),
            'actresses': v['actresses'], 'is_multi': True,
            'tags': extract_tags(v['title']), 'is_saved': False,
        }
    else:
        for a in v['actresses']: actress_index[code].add(canon_name(a))

saved_codes = {v['code'] for v in saved}
for code, vid in videos.items():
    vid['is_saved'] = code in saved_codes
    vid['actresses'] = sorted(actress_index.get(code, set()))

for s in saved:
    code = s['code']
    if code in videos: continue
    url = s.get('url', '')
    title_clean = s.get('title', '').replace(code, '').strip()
    slug_m = re.search(r'/cn/([^/?]+?)(?:\?|$)', url)
    cover_slug = slug_m.group(1) if slug_m else code.lower()
    videos[code] = {
        'code': code, 'title': title_clean,
        'url': url,
        'cover': f'https://fourhoi.com/{cover_slug}/cover-t.jpg',
        'preview': f'https://fourhoi.com/{cover_slug}/preview.mp4',
        'date': dates.get(code, ''),
        'actresses': [], 'is_multi': is_multi(code, title_clean),
        'tags': extract_tags(title_clean), 'is_saved': True,
    }

video_list = list(videos.values())
video_list.sort(key=lambda v: (not v['is_saved'], v.get('date', '') or '0'), reverse=False)

# ---- 女优分组 / 头像 / 显示名 ----
all_actresses = sorted({a for v in video_list for a in v['actresses']})

actor_ids = json.load(open(ACTOR_AVATAR_FILE, encoding='utf-8')) if ACTOR_AVATAR_FILE.exists() else {}
actress_avatars = {}
for name in all_actresses:
    if name in actor_ids: actress_avatars[name] = f'https://fourhoi.com/actress/{actor_ids[name]}-t.jpg'
    else: actress_avatars[name] = ''

actress_display = {}
for slug, info in result.items():
    name = canon_name(info['name'])
    actress_display[name] = build_display_name(name)
for v in multi:
    for a in v.get('actresses', []):
        if a not in actress_display:
            actress_display[a] = build_display_name(a)

SAVED_CODES = {v['code'] for v in saved}
SOLO_SAVED = {c for c in SAVED_CODES if c.split('-')[0] not in COMPILE_PREFIX}
DEBUT_KW = ['出道','首秀','首次亮相','钻石新人','NO.1 STYLE','デビュー','NO.1STYLE','AV debut']

# 从 MissAV 收藏女优页直接获取的权威名单
AUTH_SAVED_NAMES = [
    '八掛うみ', '皆瀬あかり', '河北彩花', '樱空桃', '伊藤舞雪',
    '明里䌷', '七泽米亚', 'miru', '宫下玲奈', '神木丽',
    '惠理', '深田咏美', '三岛奈津子', '凪ひかる', '鹫尾芽衣',
    '新有菜', '明日花绮罗', '天使萌', '凉森玲梦', '八蜜凛', '石川澪',
    '白峰美羽', 'うんぱい', '枫ふうあ', 'RARA', '新妻ゆうか',
    '松本一香', '美园和花', '森泽佳奈', '瀬户环奈', '石田佳莲',
    '幸村泉希', '白羽舞菜', '博多彩叶', '桃乃木香奈', '梦实かなえ',
    '七濑爱丽丝',
]

# 已收藏女优: 用权威名单匹配(子串)
def str_match(a, names):
    for n in names:
        if a in n or n in a: return True
    return False

# 已收藏女优: 权威名单直接匹配
actress_saved_authoritative = set()
for a in all_actresses:
    if str_match(a, AUTH_SAVED_NAMES):
        actress_saved_authoritative.add(a)

# 新人女优: result 里有出道作且不在权威收藏里
actress_rookie = set()
for slug, info in result.items():
    name = canon_name(info['name'])
    if name not in all_actresses: continue
    if str_match(name, actress_saved_authoritative): continue
    for v in info.get('top10', []):
        if any(kw in v['title'] for kw in DEBUT_KW):
            actress_rookie.add(name)

actress_groups = {}
for a in all_actresses:
    if str_match(a, actress_saved_authoritative): actress_groups[a] = 'saved'
    elif str_match(a, actress_rookie): actress_groups[a] = 'rookie'
    else: actress_groups[a] = 'other'

# ---- 标签统计 ----
tag_counter = Counter()
for v in video_list:
    for t in v['tags']: tag_counter[t] += 1
all_tags = [t for t, _ in tag_counter.most_common()]

# ---- 渲染 aid: 给每个女优写一个短 aid 加快 JS 过滤 ----
actress_aid = {a: i for i, a in enumerate(all_actresses)}
# 把视频里的 actresses 替换成 aid 数组
for v in video_list:
    v['aids'] = [actress_aid[a] for a in v.get('actresses', [])]

# ---- 输出 ----
OUT.parent.mkdir(parents=True, exist_ok=True)

# 完整数据
full = {
    'videos': video_list,
    'actresses': all_actresses,
    'actress_groups': actress_groups,
    'actress_avatars': actress_avatars,
    'actress_display': actress_display,
    'actress_aid': actress_aid,
    'tags': all_tags,
    'tag_counts': dict(tag_counter),
}
OUT.write_text(json.dumps(full, ensure_ascii=False), encoding='utf-8')

# 轻量索引: 去掉 videos 内容,只保留 counts 和元信息
idx = {k: full[k] for k in ['actresses','actress_groups','actress_avatars','actress_display','tags','tag_counts']}
idx['video_count'] = len(video_list)
idx['saved_count'] = sum(1 for v in video_list if v['is_saved'])
idx['solo_count'] = sum(1 for v in video_list if not v['is_multi'])
idx['multi_count'] = sum(1 for v in video_list if v['is_multi'])
OUT_IDX.write_text(json.dumps(idx, ensure_ascii=False), encoding='utf-8')

sc = sum(1 for v in actress_groups.values() if v=='saved')
rc = sum(1 for v in actress_groups.values() if v=='rookie')
oc = sum(1 for v in actress_groups.values() if v=='other')
print(f'作品: {len(video_list)} (单人 {idx["solo_count"]})')
print(f'女优: {len(all_actresses)} (已收藏 {sc} / 新人 {rc} / 其他 {oc})')
print(f'标签: {len(all_tags)}')
print(f'[OK] full: {OUT.stat().st_size/1024:.0f}KB  index: {OUT_IDX.stat().st_size/1024:.0f}KB')
