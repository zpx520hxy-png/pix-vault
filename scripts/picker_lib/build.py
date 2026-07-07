# -*- coding: utf-8 -*-
"""构建 missav_picker 的统一作品库 JSON (拆两版)。

- picker_data.json: 完整数据 (videos + actresses + ...)
- picker_index.json: 轻量索引 (actresses + display + avatars + groups + tags, 不含 videos)

用法:
    python build_picker_data.py

⚠️ 数据语义注意: 本模块产出两个独立"已收藏"维度, 不要混用:
  - `videos[*].is_saved` (bool, 来自 saved.json): 你收藏了这部作品
  - `actress_groups[code] == 'saved'` (来自 AUTH_SAVED_NAMES 子串匹配): 这位女优在关注名单里
  详见 `tools/missav_picker/README.md` 的"数据语义"章节。
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

# 允许从 scripts/ 目录直接运行
sys.path.insert(0, str(Path(__file__).parent.parent))

from picker_lib.paths import (
    ACTOR_AVATAR_FILE, DATES, MULTI, OUT, OUT_IDX,
    RESULT, RESULT_SOLO15, SAVED,
)
from picker_lib.tags import TAGS
from picker_lib.multi import COMPILE_PREFIX, is_multi
from picker_lib.kana import kana_to_romaji
from picker_lib.saved_actresses import AUTH_SAVED_NAMES, DEBUT_KW

# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path, default):
    """读 JSON; 不存在返回 default; 损坏抛带路径的清晰错误。"""
    if not path.exists():
        return default
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise SystemExit(f'[ERROR] JSON 损坏: {path} → {e}') from e


# ---------------------------------------------------------------------------
# 名字 / 显示名
# ---------------------------------------------------------------------------

_CJK_RE = re.compile(r'[一-鿿぀-ゟ゠-ヿ]')
_PARENS_RE = re.compile(r'[（(][^)）]*[)）]')
_KANA_RANGE_RE = re.compile(r'[぀-ゟ゠-ヿ]')
_TRAILING_DASHES_RE = re.compile(r'-+$')


def build_display_name(name):
    """含假名时, 在日文名后追加罗马字 (例: '深田咏美 (深田えいみ) [Fukada Eimi]')。"""
    if _KANA_RANGE_RE.search(name):
        clean = _PARENS_RE.sub('', name)
        romaji = _TRAILING_DASHES_RE.sub('', kana_to_romaji(clean)).strip()
        if romaji and romaji != name:
            return name + '  [' + romaji + ']'
    return name


# ---------------------------------------------------------------------------
# 名字集合 + 标准化
# ---------------------------------------------------------------------------

def _collect_actress_names(result, multi):
    """从 result + multi 里提取所有女优显示名(含拆括号后的别名)。"""
    raw = set()
    for info in result.values():
        name = info['name']
        raw.add(name)
        for part in re.split(r'[（）()\s]+', name):
            if len(part) >= 2 and _CJK_RE.search(part):
                raw.add(part)
    for v in multi:
        for a in v.get('actresses', []):
            raw.add(a)
            for part in re.split(r'[（）()\s]+', a):
                if len(part) >= 2 and _CJK_RE.search(part):
                    raw.add(part)
    return raw


# 同一女优不同拼写 → canonical
ACTOR_ALIASES = {
    '新有菜 (桥本有菜) (新ありな (橋本ありな))': ['桥本有菜 (新有菜)'],
}
ACTOR_CANON = {}
for _canon, _aliases in ACTOR_ALIASES.items():
    for _a in _aliases:
        ACTOR_CANON[_a] = _canon


def canon_name(name):
    return ACTOR_CANON.get(name, name)


# ---------------------------------------------------------------------------
# 标签提取
# ---------------------------------------------------------------------------

def make_strip_and_extract(sorted_names):
    """返回 (strip, extract) 两个闭包,共享已排序的名字列表。"""
    def strip_actress_names(title):
        clean = title
        for n in sorted_names:
            clean = clean.replace(n, '')
        return clean

    def extract_tags(title):
        clean = strip_actress_names(title)
        out = []
        for tag, keywords in TAGS:
            for kw in keywords:
                if kw in clean:
                    out.append(tag)
                    break
        return out

    return strip_actress_names, extract_tags


# ---------------------------------------------------------------------------
# URL 拼装 (cover / preview)
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r'/cn/([^/?]+?)(?:\?|$)')


def _cover_and_preview(url, code):
    slug_m = _SLUG_RE.search(url)
    slug = slug_m.group(1) if slug_m else code.lower()
    return (
        f'https://fourhoi.com/{slug}/cover-t.jpg',
        f'https://fourhoi.com/{slug}/preview.mp4',
    )


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    result = _load_json(RESULT_SOLO15, None) or _load_json(RESULT, None)
    if result is None:
        raise SystemExit(f'[ERROR] 缺主数据: {RESULT_SOLO15} 和 {RESULT} 都不存在')
    multi = _load_json(MULTI, [])
    dates = _load_json(DATES, {})
    saved = _load_json(SAVED, [])

    # 名字集(按长度倒序,优先匹配长名)
    raw_names = _collect_actress_names(result, multi)
    names_sorted = sorted(raw_names, key=len, reverse=True)
    _, extract_tags = make_strip_and_extract(names_sorted)

    # 拼作品库
    videos = {}
    actress_index = {}

    for _slug, info in result.items():
        name = info['name']
        for v in info.get('top10', []):
            code = v['code']
            title_clean = v['title'].replace(code, '').strip()
            url = v['url']
            cover, preview = _cover_and_preview(url, code)
            if code not in videos:
                videos[code] = {
                    'code': code, 'title': title_clean, 'url': url,
                    'cover': cover, 'preview': preview,
                    'date': dates.get(code, ''),
                    'is_multi': is_multi(code, title_clean),
                    'tags': extract_tags(title_clean),
                    'is_saved': False,
                }
                actress_index[code] = set()
            actress_index[code].add(canon_name(name))

    for v in multi:
        code = v['code']
        cs = v['slug']
        cover, preview = _cover_and_preview(cs and f'/cn/{cs}' or '', code)
        if code not in videos:
            videos[code] = {
                'code': code, 'title': v['title'], 'url': v['url'],
                'cover': cover, 'preview': preview,
                'date': dates.get(code, ''),
                'actresses': v['actresses'], 'is_multi': True,
                'tags': extract_tags(v['title']), 'is_saved': False,
            }
        else:
            for a in v['actresses']:
                actress_index[code].add(canon_name(a))

    saved_codes = {v['code'] for v in saved}
    for code, vid in videos.items():
        vid['is_saved'] = code in saved_codes
        vid['actresses'] = sorted(actress_index.get(code, set()))

    # saved 里有但 result/multi 都没有的视频
    for s in saved:
        code = s['code']
        if code in videos:
            continue
        url = s.get('url', '')
        title_clean = s.get('title', '').replace(code, '').strip()
        cover, preview = _cover_and_preview(url, code)
        videos[code] = {
            'code': code, 'title': title_clean, 'url': url,
            'cover': cover, 'preview': preview,
            'date': dates.get(code, ''),
            'actresses': [], 'is_multi': is_multi(code, title_clean),
            'tags': extract_tags(title_clean), 'is_saved': True,
        }

    video_list = list(videos.values())
    video_list.sort(
        key=lambda v: (not v['is_saved'], v.get('date', '') or '0'),
        reverse=False,
    )

    # 女优列表 / 头像 / 显示名
    all_actresses = sorted({a for v in video_list for a in v['actresses']})

    actor_ids = _load_json(ACTOR_AVATAR_FILE, {})
    actress_avatars = {
        name: f'https://fourhoi.com/actress/{actor_ids[name]}-t.jpg'
        if name in actor_ids else ''
        for name in all_actresses
    }

    actress_display = {}
    for info in result.values():
        name = canon_name(info['name'])
        actress_display[name] = build_display_name(name)
    for v in multi:
        for a in v.get('actresses', []):
            if a not in actress_display:
                actress_display[a] = build_display_name(a)

    # 分组: saved / rookie / other
    def _str_match(a, names):
        return any(a in n or n in a for n in names)

    saved_authoritative = {a for a in all_actresses if _str_match(a, AUTH_SAVED_NAMES)}

    rookie = set()
    for info in result.values():
        name = canon_name(info['name'])
        if name not in all_actresses:
            continue
        if _str_match(name, saved_authoritative):
            continue
        for v in info.get('top10', []):
            if any(kw in v['title'] for kw in DEBUT_KW):
                rookie.add(name)
                break

    actress_groups = {}
    for a in all_actresses:
        if _str_match(a, saved_authoritative):
            actress_groups[a] = 'saved'
        elif _str_match(a, rookie):
            actress_groups[a] = 'rookie'
        else:
            actress_groups[a] = 'other'

    # 标签统计 + 单遍统计 saved/rookie/other
    tag_counter = Counter()
    group_counter = Counter()
    saved_v = solo_v = multi_v = 0
    for v in video_list:
        for t in v['tags']:
            tag_counter[t] += 1
        if v['is_saved']:
            saved_v += 1
        if v['is_multi']:
            multi_v += 1
        else:
            solo_v += 1
    group_counter.update(actress_groups.values())

    all_tags = [t for t, _ in tag_counter.most_common()]

    # aid 短码 (前端过滤加速)
    actress_aid = {a: i for i, a in enumerate(all_actresses)}
    for v in video_list:
        v['aids'] = [actress_aid[a] for a in v.get('actresses', [])]

    # ---- 落盘 ----
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT_IDX.parent.mkdir(parents=True, exist_ok=True)

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
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(full, f, ensure_ascii=False)

    idx = {k: full[k] for k in [
        'actresses', 'actress_groups', 'actress_avatars',
        'actress_display', 'tags', 'tag_counts',
    ]}
    idx['video_count'] = len(video_list)
    idx['saved_count'] = saved_v
    idx['solo_count'] = solo_v
    idx['multi_count'] = multi_v
    with open(OUT_IDX, 'w', encoding='utf-8') as f:
        json.dump(idx, f, ensure_ascii=False)

    print(f'作品: {len(video_list)} (单人 {solo_v} / 多人 {multi_v} / 已收藏 {saved_v})')
    print(f'女优: {len(all_actresses)} '
          f'(已收藏 {group_counter.get("saved", 0)} / '
          f'新人 {group_counter.get("rookie", 0)} / '
          f'其他 {group_counter.get("other", 0)})')
    print(f'标签: {len(all_tags)}')
    print(f'[OK] full:  {OUT.stat().st_size/1024:.0f}KB')
    print(f'[OK] index: {OUT_IDX.stat().st_size/1024:.0f}KB')


if __name__ == '__main__':
    main()
