# -*- coding: utf-8 -*-
"""路径常量。统一改这里即可。"""
from pathlib import Path

ROOT = Path('D:/360MoveData/Users/Pda/Desktop/claude')

# 输入
RESULT_SOLO15 = ROOT / 'scripts/missav_scrape/result_solo15.json'
RESULT = ROOT / 'scripts/missav_scrape/result.json'
MULTI = ROOT / 'scripts/missav_scrape/multi_top30.json'
DATES = ROOT / 'scripts/missav_scrape/dates.json'
SAVED = ROOT / 'scripts/missav_scrape/saved.json'
ACTOR_AVATAR_FILE = ROOT / 'scripts/missav_scrape/actress_avatars.json'

# 输出
OUT = ROOT / 'tools/missav_picker/picker_data.json'
OUT_IDX = ROOT / 'tools/missav_picker/picker_index.json'
