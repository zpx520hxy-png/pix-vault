# -*- coding: utf-8 -*-
"""组装 HTML + 复制数据 JSON 到输出目录"""
import shutil
from pathlib import Path

ROOT = Path('D:/360MoveData/Users/Pda/Desktop/claude/tools/missav_picker')
TPL = ROOT / 'index_template.html'
JSON_PATH = ROOT / 'picker_data.json'
OUT = ROOT / 'index.html'

tpl = TPL.read_text(encoding='utf-8')
data = JSON_PATH.read_text(encoding='utf-8')
data_safe = data.replace('</script>', '<\\/script>')

html = tpl.replace('__DATA_JSON_PLACEHOLDER__', data_safe)
OUT.write_text(html, encoding='utf-8')

print(f'[OK] {OUT} ({OUT.stat().st_size:,} bytes)')
print(f'  template: {len(tpl):,} chars (content only)')
print(f'  data:     {len(data):,} chars')
print(f'  output:   {len(html):,} chars')
