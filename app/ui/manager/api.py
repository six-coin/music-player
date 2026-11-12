"""管理器的后端接口。

每个改变状态的方法都返回完整快照；读取方法返回数据。非法参数不抛异常，
原样返回当前快照——网页拿到 Python traceback 是最难排查的一类问题。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from app import i18n, paths
from app.core.library import Library
from app.core.playlists import PlaylistStore
from app.core.stats import StatsStore
from app.settings import SettingsStore
from app.system import theme as theme_tool

SECTIONS = ("overview", "songs", "playlists", "tags", "authors", "settings")
RECENT_LIMIT = 5


class ManagerApi:
    def __init__(self, config_dir: Path | None = None) -> None:
        base = config_dir or paths.CONFIG_DIR
        self.library = Library(base / "library.json")
        self.playlists = PlaylistStore(base / "playlists.json")
        self.settings = SettingsStore(base / "settings.json")
        self.stats = StatsStore(base / "stats")
        self.warnings: list[str] = []
        self.section = "overview"
        self._lock = threading.RLock()
        self._window = None
        self._load()

    # ---------- 启动 ----------

    def _load(self) -> None:
        self.warnings.extend(self.settings.load())
        language = self.settings.get("common", "language", default=i18n.DEFAULT_LANGUAGE)
        i18n.set_language(str(language))
        self.warnings.extend(self.library.load())
        self.warnings.extend(self.playlists.load())

    def attach(self, window) -> None:
        self._window = window

    def close(self) -> None:
        self.library.save()
        self.playlists.save()

    # ---------- 读取 ----------

    def get_strings(self) -> dict[str, str]:
        return i18n.strings()

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot()

    def select_section(self, section: str) -> dict[str, Any]:
        with self._lock:
            if section in SECTIONS:
                self.section = section
            return self._snapshot()

    # ---------- 快照 ----------

    def _snapshot(self) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "",
            "section": self.section,
            "selection": None,
            "language": i18n.current(),
            "theme": theme_tool.resolve(
                str(self.settings.get("common", "theme", default="system"))
            ),
            "library": self._library_payload(),
            "playlists": self._playlist_payload(),
            "settings": self.settings.data,
            "counts": self._counts(),
            "overview": self._overview(),
            "warnings": list(self.warnings),
            "errors": [],
        }

    def _library_payload(self) -> dict[str, Any]:
        return {
            "authors": [author.to_dict() for author in self.library.authors.values()],
            "tag_groups": [
                group.to_dict()
                for group in sorted(self.library.tag_groups.values(), key=lambda item: item.name)
            ],
            "musics": [self._music_payload(music) for music in self._sorted_musics()],
        }

    def _music_payload(self, music) -> dict[str, Any]:
        payload = music.to_dict()
        payload["title"] = music.title
        payload["authors_text"] = "、".join(self.library.music_authors(music))
        return payload

    def _sorted_musics(self) -> list:
        return sorted(self.library.musics.values(), key=lambda item: item.title.lower())

    def _playlist_payload(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for playlist in self.playlists.all():
            payload = playlist.to_dict()
            payload["title"] = playlist.name or i18n.t("overview.default_playlist")
            try:
                payload["count"] = len(self.playlists.resolve(playlist.uid, self.library).md5s)
            except Exception:  # 循环引用不该让整个快照失败
                payload["count"] = 0
            result.append(payload)
        return sorted(result, key=lambda item: (not item["builtin"], item["title"]))

    def _counts(self) -> dict[str, int]:
        counts = self.library.counts()
        counts["playlists"] = len(self.playlists.items)
        return counts

    def _overview(self) -> dict[str, Any]:
        now = int(time.time())
        musics = sorted(
            self.library.musics.values(), key=lambda item: item.created_at, reverse=True
        )
        recent_imported = [
            {
                "kind": "music",
                "md5": music.md5,
                "title": music.title,
                "subtitle": "、".join(self.library.music_authors(music)),
                "at": music.created_at,
            }
            for music in musics[:RECENT_LIMIT]
        ]

        edited: list[dict[str, Any]] = [
            {
                "kind": "music",
                "md5": music.md5,
                "title": music.title,
                "subtitle": "、".join(self.library.music_authors(music)),
                "at": music.updated_at or music.created_at,
            }
            for music in self.library.musics.values()
        ]
        edited.extend(
            {
                "kind": "playlist",
                "uid": playlist.uid,
                "title": playlist.name or i18n.t("overview.default_playlist"),
                "subtitle": i18n.t("nav.playlists"),
                "at": playlist.updated_at or playlist.created_at,
            }
            for playlist in self.playlists.all()
        )
        edited.sort(key=lambda item: item["at"], reverse=True)

        issues: list[dict[str, Any]] = []
        missing_tag = self.library.tag_violations()
        if missing_tag:
            issues.append({"kind": "missing_tag", "count": len(missing_tag)})
        missing_file = self.library.missing_files()
        if missing_file:
            issues.append({"kind": "missing_file", "count": len(missing_file)})

        return {
            "recent_imported": recent_imported,
            "recent_edited": edited[:RECENT_LIMIT],
            "issues": issues,
            "generated_at": now,
        }
