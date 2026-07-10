#!/usr/bin/env python
"""AV Roulette Browser main entry (compat wrapper).

Keeps the original startup path `python server.py` working while
delegating implementation to the modular v2 server package.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from server.app import run  # noqa: E402


if __name__ == "__main__":
    run()
