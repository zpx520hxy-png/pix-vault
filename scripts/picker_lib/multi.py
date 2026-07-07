# -*- coding: utf-8 -*-
"""多人/合集作品判定规则。

- COMPILE_PREFIX: 合集系列前缀(全部标为多人/合集; 不含普通剧情系列)
- MULTI_KEYWORDS: 标题中含任意关键词即标为合集
- MULTI_QTY_RE: 标题中"X 位 / X 人 / X 部 / X 张"等量化短语
"""
import re

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
    if prefix in COMPILE_PREFIX:
        return True
    if any(kw in title for kw in MULTI_KEYWORDS):
        return True
    return bool(MULTI_QTY_RE.search(title))
