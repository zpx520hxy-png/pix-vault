import json
import time
from pathlib import Path

from .config import SYNC_STATE_FILE


def read_sync_state():
    if not SYNC_STATE_FILE.is_file():
        return b'{"version":1,"updatedAt":0}'
    return SYNC_STATE_FILE.read_bytes()


def save_sync_state(body_bytes):
    try:
        payload = json.loads(body_bytes.decode("utf-8"))
        payload["updatedAt"] = int(time.time() * 1000)
        tmp = SYNC_STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        import os

        os.replace(tmp, SYNC_STATE_FILE)
        return True
    except Exception:
        return False


def get_jable_codes():
    from .config import DATA_FILES

    data_file = DATA_FILES["jable"]
    if not data_file.is_file():
        return []
    try:
        data = json.loads(data_file.read_text(encoding="utf-8"))
        return [
            v.get("code", "").lower() for v in data.get("videos", []) if v.get("code")
        ]
    except Exception:
        return []
