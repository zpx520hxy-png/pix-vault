#!/usr/bin/env python3
"""一次性预生成所有图片缩略图（也兼做按需补漏）。

把所有图片烤一遍，之后网格模式首次进入也是秒开。
PNG 透明压平 + LANCZOS 缩放 + JPEG 78 渐进式，磁盘占用大约是原图的 5%。

用法:
  cd pix-vault
  python prebuild_thumbs.py              # 默认 4 并发
  python prebuild_thumbs.py 8            # 自定义并发数
  python prebuild_thumbs.py --rebuild    # 删旧缩略图全量重建
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# 复用 server.py 的扫描和缩略图生成逻辑
import server


def task(img: dict) -> str:
    """一张图：跳过 / 命中 / 生成 / 失败"""
    rel = img["path"]
    src = server.ROOT / rel
    try:
        src_size = src.stat().st_size
    except OSError:
        return "skip"
    # 与 server.py /thumb 路由的判断保持一致
    if src_size < 80 * 1024 or src.suffix.lower() == ".gif":
        return "skip"

    # 先看缓存有没有
    thumb_path = server.THUMB_DIR / (rel + ".jpg")
    if thumb_path.is_file():
        try:
            if thumb_path.stat().st_mtime >= src.stat().st_mtime:
                return "hit"
        except OSError:
            pass

    thumb = server.get_thumb_path(rel, src)
    return "ok" if (thumb and thumb.is_file()) else "fail"


def main():
    args = sys.argv[1:]
    rebuild = "--rebuild" in args
    args = [a for a in args if not a.startswith("--")]
    workers = int(args[0]) if args else 4

    if not server.HAS_PIL:
        print("ERROR: 没装 Pillow。运行: pip install Pillow")
        sys.exit(1)

    if rebuild and server.THUMB_DIR.is_dir():
        print(f"--rebuild: 删除 {server.THUMB_DIR} ...")
        import shutil
        shutil.rmtree(server.THUMB_DIR)

    print(f"扫描 {server.ROOT} ...")
    t0 = time.perf_counter()
    images = server.scan_images(server.ROOT)
    t_scan = time.perf_counter() - t0
    print(f"  {len(images)} 张图，扫描用时 {t_scan*1000:.0f} ms")
    print(f"  缩略图目录: {server.THUMB_DIR}")
    print(f"  并发数: {workers}")
    print()

    server.THUMB_DIR.mkdir(parents=True, exist_ok=True)

    counts = {"ok": 0, "hit": 0, "skip": 0, "fail": 0}
    t0 = time.perf_counter()
    last_print = t0

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(task, img): img for img in images}
        done = 0
        for fut in as_completed(futures):
            try:
                r = fut.result()
            except Exception as e:
                r = "fail"
                print(f"  err: {futures[fut]['path']}: {e}")
            counts[r] += 1
            done += 1
            now = time.perf_counter()
            if now - last_print >= 1.0 or done == len(images):
                rate = done / (now - t0) if now > t0 else 0
                eta = (len(images) - done) / rate if rate > 0 else 0
                pct = 100 * done // len(images)
                print(f"  {done}/{len(images)} ({pct}%)  生成={counts['ok']} 命中={counts['hit']} 跳过={counts['skip']} 失败={counts['fail']}  {rate:.1f}/s  ETA {eta:.0f}s")
                last_print = now

    elapsed = time.perf_counter() - t0
    print()
    print(f"完成 {len(images)} 张，用时 {elapsed:.1f}s")

    # 磁盘占用
    total_bytes = 0
    total_count = 0
    for f in server.THUMB_DIR.rglob("*.jpg"):
        try:
            total_bytes += f.stat().st_size
            total_count += 1
        except OSError:
            pass
    print(f"  缩略图共 {total_count} 个，{total_bytes / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
