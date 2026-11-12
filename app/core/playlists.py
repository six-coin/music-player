"""歌单的读写与解析。

手动歌单保序，条件歌单是集合。解析是纯函数：输入歌单与音乐库，输出歌曲
标识，不写任何文件。条件之间出现循环引用时抛 ``PlaylistCycleError``，
调用方据此在对应条件行上报错。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from app.core.library import Library
from app.errors import ConfigError, DataError, PlaylistCycleError
from app.models import Adaptation, Filter, Playlist, new_uid
from app.system import atomic

PLAYLIST_VERSION = 1


@dataclass(slots=True)
class PlaylistContent:
    md5s: list[str] = field(default_factory=list)
    ordered: bool = False

    def as_set(self) -> set[str]:
        return set(self.md5s)


def make_default_playlist() -> Playlist:
    now = int(time.time())
    return Playlist(
        uid=new_uid(),
        name=None,
        builtin=True,
        kind="filter",
        entries=[],
        filters=[Filter(mode="include", target="all", values=[])],
        adaptation=Adaptation(),
        created_at=now,
        updated_at=now,
    )


class PlaylistStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.items: dict[str, Playlist] = {}
        self.default_uid = ""
        self.warnings: list[str] = []

    # ---------- 读写 ----------

    def load(self) -> list[str]:
        self.items.clear()
        self.warnings = []
        self.default_uid = ""

        if not self.path.exists():
            self._ensure_default()
            self.save()
            return []

        raw = atomic.read_json(self.path)
        if not isinstance(raw, dict):
            raise ConfigError(f"歌单结构错误：{self.path} 的顶层必须是对象")

        for item in raw.get("items") or []:
            if not isinstance(item, dict):
                self.warnings.append("歌单记录格式错误，已跳过一条")
                continue
            try:
                playlist = Playlist.from_dict(item)
                playlist.normalize()
                playlist.validate()
            except DataError as error:
                self.warnings.append(f"歌单记录已跳过：{error}")
                continue
            if playlist.uid in self.items:
                self.warnings.append(f"歌单记录重复，已跳过：{playlist.uid}")
                continue
            self.items[playlist.uid] = playlist

        declared = raw.get("default_uid")
        if isinstance(declared, str) and declared in self.items and self.items[declared].builtin:
            self.default_uid = declared
        else:
            self._ensure_default()

        return list(self.warnings)

    def _ensure_default(self) -> None:
        for playlist in self.items.values():
            if playlist.builtin:
                self.default_uid = playlist.uid
                return
        playlist = make_default_playlist()
        self.items[playlist.uid] = playlist
        self.default_uid = playlist.uid

    def save(self) -> None:
        payload = {
            "version": PLAYLIST_VERSION,
            "default_uid": self.default_uid,
            "items": [item.to_dict() for item in self.items.values()],
        }
        atomic.write_json(self.path, payload)

    # ---------- 查询 ----------

    def get(self, uid: str) -> Playlist | None:
        return self.items.get(uid)

    def default(self) -> Playlist:
        playlist = self.items.get(self.default_uid)
        if playlist is None:
            self._ensure_default()
            playlist = self.items[self.default_uid]
        return playlist

    def all(self) -> list[Playlist]:
        return list(self.items.values())

    # ---------- 编辑 ----------

    def create(self, name: str, kind: str = "manual") -> Playlist:
        now = int(time.time())
        playlist = Playlist(
            uid=new_uid(),
            name=name.strip(),
            builtin=False,
            kind=kind,
            entries=[],
            filters=[Filter()] if kind == "filter" else [],
            adaptation=Adaptation(),
            created_at=now,
            updated_at=now,
        )
        playlist.normalize()
        playlist.validate()
        self.items[playlist.uid] = playlist
        return playlist

    def remove(self, uid: str) -> bool:
        playlist = self.items.get(uid)
        if playlist is None or playlist.builtin:
            return False
        del self.items[uid]
        return True

    def touch(self, uid: str) -> None:
        playlist = self.items.get(uid)
        if playlist is not None:
            playlist.updated_at = int(time.time())

    # ---------- 解析 ----------

    def resolve(self, uid: str, library: Library) -> PlaylistContent:
        playlist = self.items.get(uid)
        if playlist is None:
            raise DataError(f"歌单不存在：{uid}")
        if playlist.kind == "manual":
            existing = [md5 for md5 in playlist.entries if md5 in library.musics]
            return PlaylistContent(existing, ordered=True)
        return PlaylistContent(sorted(self._resolve_set(uid, library, ())), ordered=False)

    def _resolve_set(self, uid: str, library: Library, stack: tuple[str, ...]) -> set[str]:
        playlist = self.items.get(uid)
        if playlist is None:
            return set()
        if playlist.kind == "manual":
            return {md5 for md5 in playlist.entries if md5 in library.musics}
        return self._resolve_filter(playlist, library, stack)

    def _resolve_filter(
        self, playlist: Playlist, library: Library, stack: tuple[str, ...]
    ) -> set[str]:
        if playlist.uid in stack:
            chain = " → ".join((*stack, playlist.uid))
            raise PlaylistCycleError(f"歌单存在循环引用：{chain}", (*stack, playlist.uid))

        current_stack = (*stack, playlist.uid)
        result: set[str] = set()
        for condition in playlist.filters:
            subset = self._evaluate(condition, library, current_stack)
            if condition.mode == "include":
                result |= subset
            else:
                result -= subset
        return result

    def _evaluate(self, condition: Filter, library: Library, stack: tuple[str, ...]) -> set[str]:
        if condition.target == "all":
            return set(library.musics)
        if condition.target == "music":
            return {value for value in condition.values if value in library.musics}
        if condition.target == "playlist":
            result: set[str] = set()
            for uid in condition.values:
                result |= self._resolve_set(uid, library, stack)
            return result
        if condition.target == "tag":
            wanted = set(condition.values)
            return {music.md5 for music in library.musics.values() if wanted & set(music.tags)}
        if condition.target == "author":
            wanted = set(condition.values)
            return {music.md5 for music in library.musics.values() if wanted & set(music.authors)}
        return set()
