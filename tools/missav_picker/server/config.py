import os
import sys
import socket
from pathlib import Path

ROOT = Path(__file__).parent.parent
PORT = int(os.environ.get("MISSAV_PICKER_PORT", "8699"))


def _windows_user_proxy():
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        ) as key:
            enabled = winreg.QueryValueEx(key, "ProxyEnable")[0]
            server = winreg.QueryValueEx(key, "ProxyServer")[0]
        if enabled and server:
            server = str(server).split(";", 1)[0].strip()
            if server and "://" not in server:
                server = "http://" + server
            return server or None
    except Exception:
        return None
    return None


UPSTREAM_PROXY = (
    (os.environ.get("MISSAV_PICKER_PROXY") or "").strip()
    or _windows_user_proxy()
    or None
)

CACHE_DIR = ROOT / ".img_cache"
SYNC_STATE_FILE = ROOT / ".shared_state.json"
BROWSER_HLS_MAP_FILE = ROOT / ".browser_hls_map.json"

CACHE_MAX_BYTES = 500 * 1024 * 1024
PLAY_CACHE_MAX_BYTES = int(
    os.environ.get("PLAY_CACHE_MAX_BYTES", str(2 * 1024 * 1024 * 1024))
)
CACHE_FAIL_TTL = 300
CACHE_OK_TTL = 7 * 24 * 3600
TREND_OK_TTL = 30 * 60
TREND_FAIL_TTL = 5 * 60

PLACEHOLDER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63f8cf0000000300010054f073b70000000049454e44ae"
    "426082"
)

DATA_FILES = {
    "missav": ROOT / "picker_data.json",
    "jable": ROOT / "jable_data.json",
    "index": ROOT / "picker_index.json",
}

JABLE_CODES_ENDPOINT = True
TREND_CACHE_DIR = CACHE_DIR / "trend"
PLAY_CACHE_DIR = CACHE_DIR / "play"
TREND_PREVIEW_CACHE_DIR = CACHE_DIR / "trend_preview"


def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def proxy_kwargs():
    return {"proxy": UPSTREAM_PROXY} if UPSTREAM_PROXY else {}
