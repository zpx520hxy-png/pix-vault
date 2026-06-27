"""通过 Playwright MCP 爬缺失女优的作品,需要手动在浏览器里跑"""
import json, re
from pathlib import Path

ROOT = Path('D:/360MoveData/Users/Pda/Desktop/claude/scripts/missav_scrape')

MISSING = [
    '八掛うみ', '皆瀬あかり', '樱空桃', '伊藤舞雪',
    '明里䌷', '七泽米亚', '宫下玲奈',
    '惠理', '明日花绮罗', '八蜜凛', '石川澪',
    '白峰美羽', 'RARA', '新妻ゆうか',
    '幸村泉希', '白羽舞菜', '桃乃木香奈', '七濑爱丽丝',
]

# 生成需要导航的 URL 列表
URLS = {}
for name in MISSING:
    # 对中文名做URL编码
    enc = name
    # 简单映射: 常用女优的 slug
    url = f'https://missav.ws/cn/actresses/{enc}'
    URLS[name] = url

# 输出为 JSON 供 Playwright 使用
out = ROOT / 'missing_actresses.json'
json.dump({'missing': MISSING, 'urls': URLS}, out, ensure_ascii=False, indent=2)
print(f'Written {len(MISSING)} missing actresses to {out}')
print('Use playwright to navigate to each URL and extract video codes')
