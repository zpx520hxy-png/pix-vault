#!/usr/bin/env python
"""MissAV Picker V2 — 模块化入口"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from server.app import run

if __name__ == "__main__":
    run()
