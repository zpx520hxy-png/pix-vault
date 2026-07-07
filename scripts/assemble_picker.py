# -*- coding: utf-8 -*-
"""组装 HTML + 复制数据 JSON 到输出目录。

模板里以精确 marker `__DATA_JSON_PLACEHOLDER__` 标记数据插入位置 (仅替换一次,
避免被多次替换)。JSON 内 `</script>` 已转义防 HTML 注入。
"""
import sys
from pathlib import Path

ROOT = Path('D:/360MoveData/Users/Pda/Desktop/claude/tools/missav_picker')
TPL = ROOT / 'index_template.html'
JSON_PATH = ROOT / 'picker_data.json'
OUT = ROOT / 'index.html'
MARKER = '__DATA_JSON_PLACEHOLDER__'

if not TPL.exists():
    sys.exit(f'[ERROR] 模板不存在: {TPL}')
if not JSON_PATH.exists():
    sys.exit(f'[ERROR] 数据不存在: {JSON_PATH} (先跑 scripts/build_picker_data.py)')

tpl = TPL.read_text(encoding='utf-8')
if tpl.count(MARKER) != 1:
    sys.exit(f'[ERROR] 模板里 {MARKER} 出现 {tpl.count(MARKER)} 次, 期望 1 次')

data = JSON_PATH.read_text(encoding='utf-8')
# JSON 内出现 </script> 会闭合外层 <script>,所以转义
data_safe = data.replace('</script>', '<\\/script>')

html = tpl.replace(MARKER, data_safe)
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(html, encoding='utf-8')

print(f'[OK] {OUT} ({OUT.stat().st_size:,} bytes)')
print(f'  template: {len(tpl):,} chars (content only)')
print(f'  data:     {len(data):,} chars')
print(f'  output:   {len(html):,} chars')
