#!/usr/bin/env python
"""AV Roulette Browser V2 - modular entry."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from server.app import run

if __name__ == "__main__":
    run()
