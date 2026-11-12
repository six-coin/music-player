"""音乐库的读写。

库是「实体」，歌单是「引用」。本模块只管实体：作者、标签组、歌曲。
引用是否成立属于完整性检查，不在这里阻断加载——一条坏记录不该让整个库打不开。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app import paths
from app.errors import ConfigError, DataError
from app.models import Author, Music, Tag, TagGroup
from app.system import atomic

LIBRARY_VERSION = 1


class Library:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.authors: dict[str, Author] = {}
        self.tag_groups: dict[str, TagGroup] = {}
        self.musics: dict[str, Music] = {}
        self.warnings: list[str] = []

    # ---------- 读写 ----------

    def load(self) -> list[str]:
        self.authors.clear()
        self.tag_groups.clear()
        self.musics.clear()
        self.warnings = []

        if not self.path.exists():
            self.save()
            return []

        raw = atomic.read_json(self.path)
        if not isinstance(raw, dict):
            raise ConfigError(f"音乐库结构错误：{self.path} 的顶层必须是对象")

        for item in raw.get("authors") or []:
            self._load_record(item, Author, self.authors, "作者")
        for item in raw.get("tag_groups") or []:
            self._load_record(item, TagGroup, self.tag_groups, "标签组")
        for item in raw.get("musics") or []:
            self._load_record(item, Music, self.musics, "歌曲", key="md5")

        return list(self.warnings)

    def _load_record(self, raw: Any, model, target: dict, label: str, key: str = "uid") -> None:
        if not isinstance(raw, dict):
            self.warnings.append(f"{label}记录格式错误，已跳过一条")
            return
        try:
            record = model.from_dict(raw)
            record.normalize()
            record.validate()
        except DataError as error:
            self.warnings.append(f"{label}记录已跳过：{error}")
            return
        identity = getattr(record, key)
        if identity in target:
            self.warnings.append(f"{label}记录重复，已跳过：{identity}")
            return
        target[identity] = record

    def save(self) -> None:
        payload = {
            "version": LIBRARY_VERSION,
            "authors": [item.to_dict() for item in self.authors.values()],
            "tag_groups": [item.to_dict() for item in self.tag_groups.values()],
            "musics": [item.to_dict() for item in self.musics.values()],
        }
        atomic.write_json(self.path, payload)

    # ---------- 查询 ----------

    def all_tags(self) -> dict[str, Tag]:
        return {tag.uid: tag for group in self.tag_groups.values() for tag in group.tags}

    def find_music(self, md5: str) -> Music | None:
        return self.musics.get(md5)

    def find_author(self, uid: str) -> Author | None:
        return self.authors.get(uid)

    def find_tag_group(self, uid: str) -> TagGroup | None:
        return self.tag_groups.get(uid)

    def author_name(self, uid: str) -> str:
        author = self.authors.get(uid)
        return author.name if author else ""

    def music_authors(self, music: Music) -> list[str]:
        names = [self.author_name(uid) for uid in music.authors]
        return [name for name in names if name]

    def counts(self) -> dict[str, int]:
        return {
            "musics": len(self.musics),
            "authors": len(self.authors),
            "tag_groups": len(self.tag_groups),
            "total_duration_ms": sum(music.duration_ms for music in self.musics.values()),
            "total_size": sum(music.size for music in self.musics.values()),
        }

    # ---------- 实体操作 ----------

    def upsert_music(self, music: Music) -> None:
        music.normalize()
        music.validate()
        self.musics[music.md5] = music

    def remove_music(self, md5: str) -> Music | None:
        return self.musics.pop(md5, None)

    def upsert_author(self, author: Author) -> None:
        author.normalize()
        author.validate()
        self.authors[author.uid] = author

    def remove_author(self, uid: str) -> Author | None:
        return self.authors.pop(uid, None)

    def upsert_tag_group(self, group: TagGroup) -> None:
        group.normalize()
        group.validate()
        self.tag_groups[group.uid] = group

    def remove_tag_group(self, uid: str) -> TagGroup | None:
        return self.tag_groups.pop(uid, None)

    # ---------- 体检 ----------

    def missing_files(self) -> list[str]:
        """记录在、文件不在的歌曲 MD5。"""
        return [
            music.md5
            for music in self.musics.values()
            if not paths.music_path(music.md5, music.ext).exists()
        ]

    def tag_violations(self) -> list[str]:
        """违反必选标签约束的歌曲 MD5。"""
        result: list[str] = []
        for music in self.musics.values():
            selected = set(music.tags)
            for group in self.tag_groups.values():
                if not group.compulsory:
                    continue
                group_tags = {tag.uid for tag in group.tags}
                if not selected & group_tags:
                    result.append(music.md5)
                    break
        return result

    def broken_references(self) -> list[str]:
        """引用了不存在的作者或标签的歌曲 MD5。"""
        known_authors = set(self.authors)
        known_tags = set(self.all_tags())
        result: list[str] = []
        for music in self.musics.values():
            if any(uid not in known_authors for uid in music.authors) or any(
                uid not in known_tags for uid in music.tags
            ):
                result.append(music.md5)
        return result
