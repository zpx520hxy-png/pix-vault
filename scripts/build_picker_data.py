# -*- coding: utf-8 -*-
"""构建 missav_picker 的统一作品库 JSON (拆两版)。

真实逻辑在 picker_lib/build.py 里;这个文件保持原入口名,方便外部脚本和
assemble_picker.py 不需要改路径。

用法:
    python scripts/build_picker_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from picker_lib.build import main

if __name__ == '__main__':
    main()
