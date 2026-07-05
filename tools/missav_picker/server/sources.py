"""数据源插件化：VideoSource 抽象基类 + Jable/Missav 实现"""

import json
import re
import time
from pathlib import Path
from abc import ABC, abstractmethod

from .config import ROOT, DATA_FILES, proxy_kwargs


class VideoSource(ABC):
    name: str
    label: str
    base_url: str

    @abstractmethod
    def get_data_file(self) -> Path: ...

    @abstractmethod
    def get_videos(self) -> list: ...

    @abstractmethod
    def get_cover_url(self, video) -> str: ...

    @abstractmethod
    def get_play_url(self, code: str) -> str: ...

    @abstractmethod
    def get_trending_url(self, period: str) -> str: ...

    @abstractmethod
    def parse_trending(self, html: str, period: str) -> list: ...


class JableSource(VideoSource):
    name = "jable"
    label = "Jable.TV"
    base_url = "https://jable.tv"

    def get_data_file(self):
        return DATA_FILES.get("jable", ROOT / "jable_data.json")

    def get_videos(self):
        f = self.get_data_file()
        if not f.is_file():
            return []
        try:
            return json.loads(f.read_text(encoding="utf-8")).get("videos", [])
        except Exception:
            return []

    def get_cover_url(self, video):
        return video.get("cover", "")

    def get_play_url(self, code):
        return f"{self.base_url}/videos/{code.lower()}/"

    def get_trending_url(self, period):
        return f"{self.base_url}/"

    def parse_trending(self, html, period):
        if not html:
            return []
        items, seen = [], set()
        for m in re.finditer(
            r"href=[\"\'](?:https?://jable\.tv)?/videos/([a-z0-9-]+)/?[\"\']",
            html,
            re.I,
        ):
            code = m.group(1).lower()
            if code in seen:
                continue
            seen.add(code)
            start = max(0, m.start() - 600)
            end = min(len(html), m.end() + 200)
            local = html[start:end]
            cover_m = re.search(
                r"(?:data-original|data-src|src)=[\"\'](https?://assets-cdn\.jable\.tv/[^\"\' ]+\.(?:jpe?g|png|webp))",
                local,
                re.I,
            )
            title_m = re.search(r"(?:alt|title|h4|h3)[^>]*>([^<]{2,200})<", local, re.I)
            items.append(
                {
                    "code": code,
                    "title": title_m.group(1).strip() if title_m else "",
                    "cover": cover_m.group(1) if cover_m else "",
                    "url": f"{self.base_url}/videos/{code}/",
                }
            )
            if len(items) >= 20:
                break
        return items

    def get_local_codes(self):
        return {v.get("code", "").lower() for v in self.get_videos() if v.get("code")}


class MissavSource(VideoSource):
    name = "missav"
    label = "MissAV"
    base_url = "https://missav.ws"

    _CODE_RE = re.compile(
        r"/(dm\d+)/cn/([A-Z0-9]{2,8}(?:-[A-Z0-9]{2,8})?)(?![A-Za-z0-9-])", re.I
    )
    _COVER_RE = re.compile(
        r"https?://[a-z0-9.-]*fourhoi\.com/[^\"' )]+cover[^\"' )]*", re.I
    )

    def get_data_file(self):
        return DATA_FILES.get("missav", ROOT / "picker_data.json")

    def get_videos(self):
        f = self.get_data_file()
        if not f.is_file():
            return []
        try:
            return json.loads(f.read_text(encoding="utf-8")).get("videos", [])
        except Exception:
            return []

    def get_cover_url(self, video):
        return video.get("cover", "")

    def get_play_url(self, code):
        return f"{self.base_url}/"

    def get_trending_url(self, period):
        return f"{self.base_url}/"

    def parse_trending(self, html, period):
        if not html:
            return []
        snippet = html
        m = re.search(
            r"<section[^>]*id=[\"\'](?:popular|trending|hot|weekly)[\"\'].*?</section>",
            html,
            re.I | re.S,
        )
        if m:
            snippet = m.group(0)
        else:
            idx = html.lower().find("<footer")
            if idx > 0:
                snippet = html[:idx]
        items, seen = [], set()
        for m in self._CODE_RE.finditer(snippet):
            dm = m.group(1)
            code = m.group(2).lower()
            if code in seen or code.endswith("cover-t.jpg"):
                continue
            seen.add(code)
            start = max(0, m.start() - 400)
            end = min(len(snippet), m.end() + 400)
            local = snippet[start:end]
            cover_m = self._COVER_RE.search(local)
            cover = cover_m.group(0) if cover_m else ""
            title = ""
            for tm in re.finditer(r"(?:alt|title)=[\"']([^\"']{1,200})[\"']", local):
                t = tm.group(1).strip()
                if t and t.lower() != code and "cover" not in t.lower():
                    title = t
                    break
            items.append(
                {
                    "code": code,
                    "title": title,
                    "cover": cover,
                    "url": f"{self.base_url}/{dm}/cn/{code}",
                }
            )
            if len(items) >= 20:
                break
        return items

    def get_local_codes(self):
        return {v.get("code", "").lower() for v in self.get_videos() if v.get("code")}


SOURCES = {
    "jable": JableSource(),
    "missav": MissavSource(),
}


def get_source(name: str) -> VideoSource:
    return SOURCES.get(name.lower(), SOURCES["missav"])
