#!/usr/bin/env python3
"""PixVault 生产环境 — 端口 8720，浏览 generated_images"""
import os
os.environ["PIXVAULT_PORT"] = "8720"
os.environ["PIXVAULT_IMAGES"] = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "generated_images")
from server import main
main()
