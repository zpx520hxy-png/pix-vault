#!/usr/bin/env python3
"""PixVault 测试环境 — 端口 8721，浏览 test_images 文件夹"""
import os
from pathlib import Path

# 测试文件夹（同目录下的 test_images）
test_dir = Path(__file__).resolve().parent / "test_images"

os.environ["PIXVAULT_PORT"] = "8721"
os.environ["PIXVAULT_IMAGES"] = str(test_dir)

from server import main
main()
