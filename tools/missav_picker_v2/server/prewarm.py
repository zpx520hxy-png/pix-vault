"""预热播放缓存：收藏 + 抽过 + 热门前 20
启动时跑一次,之后每小时跑一次
"""
import json
import threading
import time
from pathlib import Path

from .config import ROOT, SYNC_STATE_FILE, DATA_FILES
from .play_proxy import request_play, get_play_status


_PLAN_FILE = ROOT / ".cache_plan.json"
_PLAN_LOCK = threading.Lock()


def _read_state():
    try:
        if SYNC_STATE_FILE.is_file():
            return json.loads(SYNC_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _read_data(source):
    f = DATA_FILES.get(source)
    if not f or not f.is_file():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("videos", [])
    except Exception:
        return []


def collect_targets(top_n_trending=20):
    """收集要预热的作品代码 (只针对 jable 播放缓存)"""
    state = _read_state()
    targets = {}  # code -> source

    # 1. 只取 jable 收藏
    for v in state.get("favoritesJable", []):
        c = (v.get("code") or "").lower()
        if c:
            targets[c] = "jable"

    # 2. 抽过的里只取 jable
    for v in state.get("history", []):
        c = (v.get("code") or "").lower()
        src = (v.get("source") or state.get("source", "missav")).lower()
        if c and src == "jable":
            targets[c] = "jable"

    # 3. 只取 jable 热门前 20 (按本地数据排序,因为远端拿不到)
    vids = _read_data("jable")
    vids_sorted = sorted(vids, key=lambda v: v.get("date") or "", reverse=True)[:top_n_trending]
    for v in vids_sorted:
        c = (v.get("code") or "").lower()
        if c and c not in targets:
            targets[c] = "jable"

    return [{"code": c, "source": s} for c, s in targets.items()]


def prewarm(targets, max_per_run=20):
    """对每个目标 code 触发一次解析;已经在缓存里的会自动跳过"""
    queued = 0
    for t in targets[:max_per_run]:
        c = t["code"]
        result = request_play(c)
        if result.get("status") in ("started", "already_resolving", "pending"):
            queued += 1
    return queued


def _save_plan(plan, status_counts):
    with _PLAN_LOCK:
        try:
            data = {
                "ts": int(time.time()),
                "targets": plan,
                "status": status_counts,
            }
            _PLAN_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


def run_prewarm_once():
    targets = collect_targets()
    queued = prewarm(targets)
    # 触发后等待 1s 让异步任务跑起来,再统计
    time.sleep(1.0)
    status_counts = {"ready": 0, "pending": 0, "failed": 0, "not_found": 0}
    for t in targets:
        s = get_play_status(t["code"]).get("status")
        if s in status_counts:
            status_counts[s] += 1
    _save_plan(targets, status_counts)
    return {"queued": queued, "total": len(targets), "status": status_counts}


def start_prewarm_daemon(interval_seconds=3600):
    """启动后台线程,每 interval_seconds 跑一次预热"""
    def loop():
        # 启动后延迟 5 秒,避开启动期资源竞争
        time.sleep(5)
        while True:
            try:
                run_prewarm_once()
            except Exception as e:
                print(f"  [prewarm] error: {e!r}")
            time.sleep(interval_seconds)

    t = threading.Thread(target=loop, daemon=True, name="prewarm")
    t.start()
    return t


def read_plan():
    if not _PLAN_FILE.is_file():
        return None
    try:
        return json.loads(_PLAN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
