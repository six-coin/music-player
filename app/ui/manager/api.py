"""管理器的后端接口。

每个改变状态的方法都返回完整快照；读取方法返回数据。非法参数不抛异常，
原样返回当前快照——网页拿到 Python traceback 是最难排查的一类问题。
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

import webview
from loguru import logger

from app import __version__, i18n, paths
from app.core import integrity, source
from app.core.adaptation import Params, effective, skip_probability, skip_rate
from app.core.importer import ImportOutcome, import_file
from app.core.library import Library
from app.core.naming import parse_filename
from app.core.playlists import PlaylistStore
from app.core.stats import StatsStore
from app.errors import ActionError
from app.models import (
    FILTER_MODES,
    FILTER_TARGETS,
    Author,
    Filter,
    Music,
    Tag,
    TagGroup,
    new_uid,
)
from app.settings import THEMES, SettingsStore
from app.system import ffmpeg
from app.system import theme as theme_tool

SECTIONS = ("overview", "songs", "playlists", "tags", "authors", "settings")
RECENT_LIMIT = 5
AUDIO_FILTER = ("音频文件 (*.mp3;*.m4a)",)
ADAPTATION_KEYS = ("window", "min_plays", "base", "skip_seconds")


def _params_dict(params: Params) -> dict[str, Any]:
    return {
        "window": params.window,
        "min_plays": params.min_plays,
        "base": params.base,
        "skip_seconds": params.skip_seconds,
    }


class ManagerApi:
    def __init__(self, config_dir: Path | None = None) -> None:
        base = config_dir or paths.CONFIG_DIR
        self.base = base
        self.library = Library(base / "library.json")
        self.playlists = PlaylistStore(base / "playlists.json")
        self.settings = SettingsStore(base / "settings.json")
        self.stats = StatsStore(base / "stats")
        self.warnings: list[str] = []
        self.section = "overview"
        self.selection: dict[str, str] | None = None
        self.status = self._system_status()
        self._lock = threading.RLock()
        self._window = None
        self._tasks: dict[str, dict[str, Any]] = {}
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
        try:
            with self._lock:
                self.library.save()
                self.playlists.save()
        except Exception as error:  # 关闭时保存失败不该挡住窗口退出
            logger.error("退出前保存失败：{}", error)

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

    def select_item(self, kind: str, uid: str) -> dict[str, Any]:
        with self._lock:
            if kind == "music" and uid in self.library.musics:
                self.selection = {"kind": "music", "uid": uid}
                self.section = "songs"
            elif kind == "playlist" and uid in self.playlists.items:
                self.selection = {"kind": "playlist", "uid": uid}
                self.section = "playlists"
            elif kind == "tag_group" and uid in self.library.tag_groups:
                self.selection = {"kind": "tag_group", "uid": uid}
                self.section = "tags"
            elif kind == "author" and uid in self.library.authors:
                self.selection = {"kind": "author", "uid": uid}
                self.section = "authors"
            return self._snapshot()

    def clear_selection(self) -> dict[str, Any]:
        with self._lock:
            self.selection = None
            return self._snapshot()

    # ---------- 快照 ----------

    def _snapshot(self) -> dict[str, Any]:
        missing = set(self.library.missing_files())
        tag_issues = set(self.library.tag_violations())
        return {
            "ok": True,
            "message": "",
            "section": self.section,
            "selection": self.selection,
            "language": i18n.current(),
            "theme": theme_tool.resolve(
                str(self.settings.get("common", "theme", default="system"))
            ),
            "library": self._library_payload(missing, tag_issues),
            "playlists": self._playlist_payload(),
            "settings": self.settings.data,
            "status": self.status,
            "counts": self._counts(),
            "overview": self._overview(),
            "warnings": list(self.warnings),
            "errors": [],
        }

    def _library_payload(self, missing: set[str], tag_issues: set[str]) -> dict[str, Any]:
        usage = self.library.tag_usage()
        tag_groups: list[dict[str, Any]] = []
        for group in sorted(self.library.tag_groups.values(), key=lambda item: item.name):
            payload = group.to_dict()
            payload["count"] = len(self.library.tag_group_songs(group.uid))
            for tag in payload["tags"]:
                tag["count"] = usage.get(tag["uid"], 0)
            tag_groups.append(payload)

        authors: list[dict[str, Any]] = []
        for author in self.library.authors.values():
            payload = author.to_dict()
            payload["count"] = len(self.library.author_songs(author.uid))
            authors.append(payload)

        return {
            "authors": authors,
            "tag_groups": tag_groups,
            "musics": [
                self._music_payload(music, missing, tag_issues) for music in self._sorted_musics()
            ],
        }

    def _music_payload(
        self, music: Music, missing: set[str], tag_issues: set[str]
    ) -> dict[str, Any]:
        payload = music.to_dict()
        payload["title"] = music.title
        payload["authors_text"] = "、".join(self.library.music_authors(music))
        payload["missing"] = music.md5 in missing
        payload["tag_issue"] = music.md5 in tag_issues
        return payload

    def _sorted_musics(self) -> list[Music]:
        return sorted(self.library.musics.values(), key=lambda item: item.title.lower())

    def _playlist_payload(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for playlist in self.playlists.all():
            payload = playlist.to_dict()
            payload["title"] = playlist.name or i18n.t("overview.default_playlist")
            try:
                content = self.playlists.resolve(playlist.uid, self.library)
                payload["count"] = len(content.md5s)
                payload["error"] = ""
            except Exception as error:  # 循环引用不该让整个快照失败
                payload["count"] = 0
                payload["error"] = str(error)
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
        orphans = integrity.orphan_paths(self.library)
        if orphans:
            issues.append({"kind": "orphan_file", "count": len(orphans)})
        broken = self.library.broken_references()
        if broken:
            issues.append({"kind": "broken_reference", "count": len(broken)})

        return {
            "recent_imported": recent_imported,
            "recent_edited": edited[:RECENT_LIMIT],
            "issues": issues,
            "generated_at": now,
        }

    # ---------- 歌曲编辑 ----------

    def _music(self, md5: str) -> Music | None:
        return self.library.musics.get(md5)

    def _touch(self, music: Music) -> None:
        music.updated_at = int(time.time())

    def update_music_name(self, md5: str, value: str) -> dict[str, Any]:
        with self._lock:
            music = self._music(md5)
            name = (value or "").strip()
            if music is None or not name:
                return {"ok": False}
            if music.names:
                music.names[0] = name
            else:
                music.names = [name]
            self._touch(music)
            self.library.save()
            return {"ok": True}

    def set_music_authors(self, md5: str, uids: list[str]) -> dict[str, Any]:
        with self._lock:
            music = self._music(md5)
            if music is None:
                return self._snapshot()
            seen: set[str] = set()
            authors: list[str] = []
            for uid in uids or []:
                if uid in self.library.authors and uid not in seen:
                    seen.add(uid)
                    authors.append(uid)
            music.authors = authors
            self._touch(music)
            self.library.save()
            return self._snapshot()

    def toggle_music_tag(self, md5: str, tag_uid: str, on: bool) -> dict[str, Any]:
        with self._lock:
            music = self._music(md5)
            tag = self.library.all_tags().get(tag_uid)
            if music is None or tag is None:
                return self._snapshot()
            group = self._tag_group_of(tag_uid)
            tags = list(music.tags)
            if on:
                if group is not None and group.unique:
                    group_tags = {item.uid for item in group.tags}
                    tags = [uid for uid in tags if uid not in group_tags]
                if tag_uid not in tags:
                    tags.append(tag_uid)
            else:
                tags = [uid for uid in tags if uid != tag_uid]
            music.tags = tags
            self._touch(music)
            self.library.save()
            return self._snapshot()

    def _tag_group_of(self, tag_uid: str):
        for group in self.library.tag_groups.values():
            if any(tag.uid == tag_uid for tag in group.tags):
                return group
        return None

    def add_alias(self, md5: str, name: str) -> dict[str, Any]:
        with self._lock:
            music = self._music(md5)
            text = (name or "").strip()
            if music is None or not text:
                return self._snapshot()
            if text not in music.names:
                music.names.append(text)
                self._touch(music)
                self.library.save()
            return self._snapshot()

    def remove_alias(self, md5: str, index: int) -> dict[str, Any]:
        with self._lock:
            music = self._music(md5)
            if music is None:
                return self._snapshot()
            position = index + 1
            if 1 <= position < len(music.names):
                del music.names[position]
                self._touch(music)
                self.library.save()
            return self._snapshot()

    def move_alias(self, md5: str, index: int, delta: int) -> dict[str, Any]:
        with self._lock:
            music = self._music(md5)
            if music is None:
                return self._snapshot()
            source = index + 1
            target = source + delta
            if 1 <= source < len(music.names) and 1 <= target < len(music.names):
                music.names[source], music.names[target] = (
                    music.names[target],
                    music.names[source],
                )
                self._touch(music)
                self.library.save()
            return self._snapshot()

    def create_author(self, name: str) -> dict[str, Any]:
        with self._lock:
            text = (name or "").strip()
            if text and not any(author.name == text for author in self.library.authors.values()):
                self.library.upsert_author(Author(uid=new_uid(), name=text))
                self.library.save()
            return self._snapshot()

    # ---------- 标签 ----------

    def _fail(self, key: str, **values: Any) -> dict[str, Any]:
        """带一句人话的失败快照；界面直接 toast 出来。"""
        return self._fail_message(i18n.t(key, **values))

    def _fail_message(self, message: str) -> dict[str, Any]:
        snapshot = self._snapshot()
        snapshot["ok"] = False
        snapshot["message"] = message
        return snapshot

    def create_tag_group(
        self, name: str, compulsory: bool = False, unique: bool = False
    ) -> dict[str, Any]:
        with self._lock:
            text = (name or "").strip()
            if not text:
                return self._fail("tag.name_required")
            if any(group.name == text for group in self.library.tag_groups.values()):
                return self._fail("tag.group_exists", name=text)
            group = TagGroup(
                uid=new_uid(), name=text, compulsory=bool(compulsory), unique=bool(unique)
            )
            group.normalize()
            group.validate()
            self.library.upsert_tag_group(group)
            self.library.save()
            self.selection = {"kind": "tag_group", "uid": group.uid}
            self.section = "tags"
            return self._snapshot()

    def update_tag_group(self, uid: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            group = self.library.tag_groups.get(uid)
            if group is None:
                return self._snapshot()
            if isinstance(patch, dict):
                name = patch.get("name")
                if isinstance(name, str) and name.strip():
                    text = name.strip()
                    if text != group.name and any(
                        item.name == text
                        for item in self.library.tag_groups.values()
                        if item.uid != uid
                    ):
                        return self._fail("tag.group_exists", name=text)
                    group.name = text
                if isinstance(patch.get("compulsory"), bool):
                    group.compulsory = patch["compulsory"]
                if isinstance(patch.get("unique"), bool):
                    group.unique = patch["unique"]
            group.normalize()
            self.library.save()
            return self._snapshot()

    def delete_tag_group(self, uid: str, force: bool = False) -> dict[str, Any]:
        with self._lock:
            group = self.library.tag_groups.get(uid)
            if group is None:
                return self._snapshot()
            songs = self.library.tag_group_songs(uid)
            if songs and not force:
                names = "、".join(music.title for music in songs[:3])
                return self._fail("tag.group_referenced", count=len(songs), names=names)
            if songs:
                group_tags = {tag.uid for tag in group.tags}
                for music in songs:
                    music.tags = [tag_uid for tag_uid in music.tags if tag_uid not in group_tags]
                    self._touch(music)
            self.library.remove_tag_group(uid)
            self.library.save()
            if self.selection and self.selection.get("uid") == uid:
                self.selection = None
            return self._snapshot()

    def add_tag(self, group_uid: str, name: str) -> dict[str, Any]:
        with self._lock:
            group = self.library.tag_groups.get(group_uid)
            text = (name or "").strip()
            if group is None:
                return self._snapshot()
            if not text:
                return self._fail("tag.name_required")
            if any(tag.name == text for tag in group.tags):
                return self._fail("tag.exists", name=text)
            group.tags.append(Tag(uid=new_uid(), name=text))
            group.normalize()
            self.library.save()
            return self._snapshot()

    def rename_tag(self, group_uid: str, tag_uid: str, value: str) -> dict[str, Any]:
        with self._lock:
            group = self.library.tag_groups.get(group_uid)
            text = (value or "").strip()
            if group is None:
                return self._snapshot()
            tag = next((item for item in group.tags if item.uid == tag_uid), None)
            if tag is None:
                return self._snapshot()
            if not text:
                return self._fail("tag.name_required")
            if any(item.name == text and item.uid != tag_uid for item in group.tags):
                return self._fail("tag.exists", name=text)
            tag.name = text
            self.library.save()
            return self._snapshot()

    def remove_tag(self, group_uid: str, tag_uid: str) -> dict[str, Any]:
        with self._lock:
            group = self.library.tag_groups.get(group_uid)
            if group is None:
                return self._snapshot()
            group.tags = [tag for tag in group.tags if tag.uid != tag_uid]
            for music in self.library.musics.values():
                if tag_uid in music.tags:
                    music.tags = [uid for uid in music.tags if uid != tag_uid]
                    self._touch(music)
            self.library.save()
            return self._snapshot()

    # ---------- 作者 ----------

    def update_author(self, uid: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            author = self.library.authors.get(uid)
            if author is None:
                return self._snapshot()
            if isinstance(patch, dict):
                name = patch.get("name")
                if isinstance(name, str) and name.strip():
                    text = name.strip()
                    if text != author.name and any(
                        item.name == text
                        for item in self.library.authors.values()
                        if item.uid != uid
                    ):
                        return self._fail("author.exists", name=text)
                    author.name = text
                description = patch.get("description")
                if isinstance(description, str):
                    author.description = description
            author.normalize()
            self.library.save()
            return self._snapshot()

    def delete_author(self, uid: str, force: bool = False) -> dict[str, Any]:
        with self._lock:
            author = self.library.authors.get(uid)
            if author is None:
                return self._snapshot()
            songs = self.library.author_songs(uid)
            if songs and not force:
                names = "、".join(music.title for music in songs[:3])
                return self._fail("author.referenced", count=len(songs), names=names)
            for music in songs:
                music.authors = [item for item in music.authors if item != uid]
                self._touch(music)
            self.library.remove_author(uid)
            self.library.save()
            if self.selection and self.selection.get("uid") == uid:
                self.selection = None
            return self._snapshot()

    def reorder_authors(self, uids: list[str]) -> dict[str, Any]:
        with self._lock:
            self.library.reorder_authors([str(uid) for uid in uids or []])
            self.library.save()
            return self._snapshot()

    def move_author(self, uid: str, delta: int) -> dict[str, Any]:
        with self._lock:
            if self.library.move_author(uid, int(delta)):
                self.library.save()
            return self._snapshot()

    # ---------- 批量操作 ----------

    def batch_add_tags(
        self, md5s: list[str], tag_uids: list[str], clear_groups: bool = False
    ) -> dict[str, Any]:
        with self._lock:
            tags = self.library.all_tags()
            chosen = [tags[uid] for uid in tag_uids or [] if uid in tags]
            targets = [self.library.musics[md5] for md5 in md5s or [] if md5 in self.library.musics]
            group_of = {
                tag.uid: group for group in self.library.tag_groups.values() for tag in group.tags
            }
            for music in targets:
                current = list(music.tags)
                if clear_groups:
                    groups = {group_of[tag.uid].uid for tag in chosen if tag.uid in group_of}
                    group_tags = {
                        item.uid
                        for group in self.library.tag_groups.values()
                        if group.uid in groups
                        for item in group.tags
                    }
                    current = [uid for uid in current if uid not in group_tags]
                for tag in chosen:
                    group = group_of.get(tag.uid)
                    if group is not None and group.unique:
                        group_tags = {item.uid for item in group.tags}
                        current = [uid for uid in current if uid not in group_tags]
                    if tag.uid not in current:
                        current.append(tag.uid)
                music.tags = current
                self._touch(music)
            if targets:
                self.library.save()
            return self._snapshot()

    def batch_add_to_playlist(self, md5s: list[str], playlist_uid: str) -> dict[str, Any]:
        with self._lock:
            playlist = self.playlists.get(playlist_uid)
            if playlist is None or playlist.kind != "manual":
                return self._snapshot()
            existing = set(playlist.entries)
            added = 0
            for md5 in md5s or []:
                if md5 in self.library.musics and md5 not in existing:
                    playlist.entries.append(md5)
                    existing.add(md5)
                    added += 1
            if added:
                self.playlists.touch(playlist.uid)
                self.playlists.save()
            return self._snapshot()

    # ---------- 歌单编辑 ----------

    def create_playlist(self, name: str, kind: str) -> dict[str, Any]:
        with self._lock:
            text = (name or "").strip()
            if not text or kind not in ("manual", "filter"):
                snapshot = self._snapshot()
                snapshot["ok"] = False
                snapshot["message"] = i18n.t("playlist.invalid")
                return snapshot
            playlist = self.playlists.create(text, kind)
            self.playlists.save()
            self.selection = {"kind": "playlist", "uid": playlist.uid}
            self.section = "playlists"
            return self._snapshot()

    def update_playlist_name(self, uid: str, value: str) -> dict[str, Any]:
        with self._lock:
            playlist = self.playlists.get(uid)
            text = (value or "").strip()
            if playlist is None or playlist.builtin or not text:
                return {"ok": False}
            playlist.name = text
            self.playlists.touch(uid)
            self.playlists.save()
            return {"ok": True}

    def delete_playlist(self, uid: str) -> dict[str, Any]:
        with self._lock:
            playlist = self.playlists.get(uid)
            if playlist is None or playlist.builtin:
                return self._snapshot()
            referrers = self._playlist_referrers(uid)
            if referrers:
                snapshot = self._snapshot()
                snapshot["ok"] = False
                snapshot["message"] = i18n.t("playlist.referenced", names="、".join(referrers))
                return snapshot
            self.playlists.remove(uid)
            self.playlists.save()
            for suffix in (".json", ".lock"):
                self.stats.path_for(uid).with_suffix(suffix).unlink(missing_ok=True)
            if self.selection and self.selection.get("uid") == uid:
                self.selection = None
            return self._snapshot()

    def _playlist_referrers(self, uid: str) -> list[str]:
        names: list[str] = []
        for playlist in self.playlists.items.values():
            if playlist.uid == uid:
                continue
            for condition in playlist.filters:
                if condition.target == "playlist" and uid in condition.values:
                    names.append(playlist.name or i18n.t("overview.default_playlist"))
                    break
        return names

    def set_playlist_entries(self, uid: str, md5s: list[str]) -> dict[str, Any]:
        with self._lock:
            playlist = self.playlists.get(uid)
            if playlist is None or playlist.kind != "manual":
                return self._snapshot()
            seen: set[str] = set()
            entries: list[str] = []
            for md5 in md5s or []:
                if md5 in self.library.musics and md5 not in seen:
                    seen.add(md5)
                    entries.append(md5)
            playlist.entries = entries
            self.playlists.touch(uid)
            self.playlists.save()
            return self._snapshot()

    def add_playlist_songs(self, uid: str, md5s: list[str]) -> dict[str, Any]:
        with self._lock:
            playlist = self.playlists.get(uid)
            if playlist is None or playlist.kind != "manual":
                return self._snapshot()
            existing = set(playlist.entries)
            for md5 in md5s or []:
                if md5 in self.library.musics and md5 not in existing:
                    playlist.entries.append(md5)
                    existing.add(md5)
            self.playlists.touch(uid)
            self.playlists.save()
            return self._snapshot()

    def remove_playlist_song(self, uid: str, md5: str) -> dict[str, Any]:
        with self._lock:
            playlist = self.playlists.get(uid)
            if playlist is None or playlist.kind != "manual":
                return self._snapshot()
            playlist.entries = [item for item in playlist.entries if item != md5]
            self.playlists.touch(uid)
            self.playlists.save()
            return self._snapshot()

    def add_filter(self, uid: str) -> dict[str, Any]:
        with self._lock:
            playlist = self.playlists.get(uid)
            if playlist is None or playlist.kind != "filter":
                return self._snapshot()
            playlist.filters.append(Filter(mode="include", target="music", values=[]))
            self.playlists.touch(uid)
            self.playlists.save()
            return self._snapshot()

    def update_filter(self, uid: str, index: int, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            playlist = self.playlists.get(uid)
            if playlist is None or playlist.kind != "filter":
                return self._snapshot()
            if not 0 <= index < len(playlist.filters):
                return self._snapshot()
            condition = playlist.filters[index]
            if isinstance(patch, dict):
                mode = patch.get("mode")
                if mode in FILTER_MODES:
                    condition.mode = mode
                target = patch.get("target")
                if target in FILTER_TARGETS:
                    condition.target = target
                values = patch.get("values")
                if isinstance(values, list):
                    condition.values = [str(value) for value in values]
            condition.normalize()
            self.playlists.touch(uid)
            self.playlists.save()
            return self._snapshot()

    def remove_filter(self, uid: str, index: int) -> dict[str, Any]:
        with self._lock:
            playlist = self.playlists.get(uid)
            if playlist is None or playlist.kind != "filter":
                return self._snapshot()
            if 0 <= index < len(playlist.filters):
                del playlist.filters[index]
                self.playlists.touch(uid)
                self.playlists.save()
            return self._snapshot()

    def move_filter(self, uid: str, index: int, delta: int) -> dict[str, Any]:
        with self._lock:
            playlist = self.playlists.get(uid)
            if playlist is None or playlist.kind != "filter":
                return self._snapshot()
            target = index + delta
            if 0 <= index < len(playlist.filters) and 0 <= target < len(playlist.filters):
                playlist.filters[index], playlist.filters[target] = (
                    playlist.filters[target],
                    playlist.filters[index],
                )
                self.playlists.touch(uid)
                self.playlists.save()
            return self._snapshot()

    def get_playlist_songs(self, uid: str) -> dict[str, Any]:
        with self._lock:
            try:
                content = self.playlists.resolve(uid, self.library)
            except Exception as error:
                return {"ok": False, "message": str(error), "items": []}
            missing = set(self.library.missing_files())
            tag_issues = set(self.library.tag_violations())
            items = [
                self._music_payload(self.library.musics[md5], missing, tag_issues)
                for md5 in content.md5s
                if md5 in self.library.musics
            ]
            return {"ok": True, "ordered": content.ordered, "items": items}

    # ---------- 自适应 ----------

    def update_adaptation(self, uid: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            playlist = self.playlists.get(uid)
            if playlist is None:
                return self._snapshot()
            if isinstance(patch, dict):
                if isinstance(patch.get("enabled"), bool):
                    playlist.adaptation.enabled = patch["enabled"]
                for key in ADAPTATION_KEYS:
                    if key not in patch:
                        continue
                    value = patch[key]
                    if value is None:
                        setattr(playlist.adaptation, key, None)
                        continue
                    try:
                        setattr(
                            playlist.adaptation,
                            key,
                            float(value) if key == "base" else int(value),
                        )
                    except (TypeError, ValueError):
                        continue
            playlist.adaptation.normalize()
            self.playlists.touch(uid)
            self.playlists.save()
            return self._snapshot()

    def get_playlist_stats(self, uid: str) -> dict[str, Any]:
        """统计抽屉的数据：参数、每首歌的记录数与下次跳过概率。"""
        with self._lock:
            playlist = self.playlists.get(uid)
            if playlist is None:
                return {"ok": False, "rows": []}
            defaults = self._adaptation_defaults()
            params = effective(playlist.adaptation, defaults)
            try:
                content = self.playlists.resolve(uid, self.library)
            except Exception as error:
                return {"ok": False, "message": str(error), "rows": []}

            summary = self.stats.summary(uid)
            rows: list[dict[str, Any]] = []
            for md5 in content.md5s:
                music = self.library.musics.get(md5)
                if music is None:
                    continue
                item = summary.get(md5) or {}
                records = str(item.get("records", ""))
                rows.append(
                    {
                        "md5": md5,
                        "title": music.title,
                        "total": len(records),
                        "skips": records.count("1"),
                        "rate": skip_rate(records),
                        "auto_skipped": int(item.get("auto_skipped", 0) or 0),
                        "probability": skip_probability(records, params),
                    }
                )
            return {
                "ok": True,
                "enabled": playlist.adaptation.enabled,
                "params": _params_dict(params),
                "defaults": _params_dict(defaults),
                "overridden": {
                    key: getattr(playlist.adaptation, key) is not None for key in ADAPTATION_KEYS
                },
                "rows": rows,
            }

    def get_music_stats(self, md5: str) -> dict[str, Any]:
        """一首歌在各个歌单里的记录情况，供歌曲详情的「自适应」卡片使用。"""
        with self._lock:
            if md5 not in self.library.musics:
                return {"ok": False, "playlists": [], "total": 0, "skips": 0, "rate": 0.0}
            defaults = self._adaptation_defaults()
            rows: list[dict[str, Any]] = []
            total = 0
            skips = 0
            for playlist in self.playlists.all():
                summary = self.stats.summary(playlist.uid).get(md5)
                if not summary:
                    continue
                params = effective(playlist.adaptation, defaults)
                count = int(summary["total"])
                rows.append(
                    {
                        "uid": playlist.uid,
                        "title": playlist.name or i18n.t("overview.default_playlist"),
                        "enabled": playlist.adaptation.enabled,
                        "total": count,
                        "skips": int(summary["skips"]),
                        "rate": float(summary["rate"]),
                        "auto_skipped": int(summary["auto_skipped"]),
                        "probability": skip_probability(str(summary["records"]), params),
                    }
                )
                total += count
                skips += int(summary["skips"])
            return {
                "ok": True,
                "playlists": rows,
                "total": total,
                "skips": skips,
                "rate": skips / total if total else 0.0,
            }

    def reset_stats(self, uid: str, md5: str = "") -> dict[str, Any]:
        with self._lock:
            if self.playlists.get(uid) is None:
                return self._snapshot()
            if md5:
                self.stats.drop(uid, md5)
            else:
                self.stats.reset(uid)
            snapshot = self._snapshot()
            snapshot["message"] = i18n.t("adaptation.cleared")
            return snapshot

    # ---------- 导入 ----------

    def browse_import(self) -> dict[str, Any]:
        if self._window is None:
            return {"paths": []}
        start_dir = str(
            paths.resolve_user_path(str(self.settings.get("import", "dir", default="")))
        )
        try:
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                directory=start_dir,
                allow_multiple=True,
                file_types=AUDIO_FILTER,
            )
        except Exception as error:
            logger.error("打开文件对话框失败：{}", error)
            return {"paths": [], "message": str(error)}
        if not result:
            return {"paths": []}
        if isinstance(result, str):
            return {"paths": [result]}
        return {"paths": [str(item) for item in result]}

    def preview_import(self, paths_list: list[str]) -> dict[str, Any]:
        """把文件名拆成标题与作者，供批量向导逐条修改。"""
        items: list[dict[str, Any]] = []
        for raw in paths_list or []:
            path = Path(str(raw))
            title, authors = parse_filename(path.stem)
            items.append(
                {
                    "path": str(path),
                    "filename": path.name,
                    "title": title,
                    "authors": authors,
                }
            )
        return {"items": items}

    def start_import(self, items: list[Any], clean: bool | None = None) -> dict[str, Any]:
        normalized: list[dict[str, Any]] = []
        for item in items or []:
            if isinstance(item, str):
                normalized.append({"path": item, "title": None, "authors": None})
            elif isinstance(item, dict) and item.get("path"):
                authors = item.get("authors")
                normalized.append(
                    {
                        "path": str(item["path"]),
                        "title": item.get("title"),
                        "authors": (
                            [str(name) for name in authors] if isinstance(authors, list) else None
                        ),
                    }
                )
        if not normalized:
            return {"task_id": ""}

        task_id = new_uid()
        with self._lock:
            self._tasks[task_id] = {
                "state": "running",
                "done": 0,
                "total": len(normalized),
                "current": "",
                "imported": [],
                "errors": [],
                "clean": clean,
            }
        thread = threading.Thread(
            target=self._run_import, args=(task_id, normalized), name="import", daemon=True
        )
        thread.start()
        return {"task_id": task_id}

    def _run_import(self, task_id: str, items: list[dict[str, Any]]) -> None:
        default_clean = bool(self.settings.get("import", "clean_audio", default=True))
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            clean = default_clean if task.get("clean") is None else bool(task["clean"])

        for index, entry in enumerate(items, start=1):
            path = Path(entry["path"])
            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    return
                task["current"] = path.name
            try:
                outcome: ImportOutcome = import_file(
                    path,
                    self.library,
                    clean=clean,
                    title=entry.get("title"),
                    authors=entry.get("authors"),
                )
            except Exception as error:  # 单个文件失败不打断整批
                logger.exception("导入失败：{}", entry["path"])
                outcome = ImportOutcome(error=str(error))
            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    return
                if outcome.error:
                    task["errors"].append(f"{path.name}：{outcome.error}")
                elif outcome.duplicate:
                    task["errors"].append(f"{path.name}：{i18n.t('import.duplicate')}")
                else:
                    task["imported"].append(outcome.music.md5)
                    self.library.save()
                task["done"] = index
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task["state"] = "done"
                task["current"] = ""

    def poll_task(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return {"state": "missing", "done": 0, "total": 0, "current": "", "errors": []}
            return {
                "state": task["state"],
                "kind": task.get("kind", ""),
                "done": task["done"],
                "total": task["total"],
                "current": task["current"],
                "imported": list(task["imported"]),
                "errors": list(task["errors"]),
                "result": task.get("result"),
            }

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task["cancel"] = True
            return {"ok": task is not None}

    # ---------- 换源与删除 ----------

    def browse_audio(self) -> dict[str, Any]:
        """换源用的单文件选择。"""
        if self._window is None:
            return {"path": ""}
        start_dir = str(
            paths.resolve_user_path(str(self.settings.get("import", "dir", default="")))
        )
        try:
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                directory=start_dir,
                allow_multiple=False,
                file_types=AUDIO_FILTER,
            )
        except Exception as error:
            logger.error("打开文件对话框失败：{}", error)
            return {"path": "", "message": str(error)}
        if not result:
            return {"path": ""}
        if isinstance(result, str):
            return {"path": result}
        return {"path": str(result[0]) if result else ""}

    def _adaptation_defaults(self) -> Params:
        data = self.settings.get("common", "adaptation", default={})
        if not isinstance(data, dict):
            data = {}
        return Params(
            window=int(data.get("window", 100)),
            min_plays=int(data.get("min_plays", 10)),
            base=float(data.get("base", 0.95)),
            skip_seconds=int(data.get("skip_seconds", 30)),
        )

    def start_replace_source(self, md5: str, path: str) -> dict[str, Any]:
        with self._lock:
            if md5 not in self.library.musics:
                return {"task_id": ""}
        task_id = new_uid()
        with self._lock:
            self._tasks[task_id] = {
                "state": "running",
                "kind": "replace",
                "done": 0,
                "total": 1,
                "current": "",
                "imported": [],
                "errors": [],
                "result": None,
            }
        thread = threading.Thread(
            target=self._run_replace, args=(task_id, md5, path), name="replace", daemon=True
        )
        thread.start()
        return {"task_id": task_id}

    def _run_replace(self, task_id: str, md5: str, path: str) -> None:
        clean = bool(self.settings.get("import", "clean_audio", default=True))
        try:
            prepared = source.prepare_replacement(Path(path), clean)
        except ActionError as error:
            self._finish_task(task_id, error=str(error))
            return
        except Exception as error:  # 未预料的失败也要让界面能退出进度框
            logger.exception("换源准备失败")
            self._finish_task(task_id, error=str(error))
            return

        with self._lock:
            music = self.library.musics.get(md5)
            if music is None:
                prepared.temp.unlink(missing_ok=True)
                self._finish_task(task_id, error=i18n.t("song.deleted_elsewhere"))
                return
            try:
                report = source.apply_replacement(
                    music,
                    prepared,
                    self.library,
                    self.playlists,
                    self.stats,
                    self._adaptation_defaults(),
                )
            except ActionError as error:
                self._finish_task(task_id, error=str(error))
                return
            except Exception as error:
                logger.exception("换源失败")
                self._finish_task(task_id, error=str(error))
                return
            self.selection = {"kind": "music", "uid": report.new_md5}
            self.section = "songs"
            self._finish_task(
                task_id,
                result={
                    "title": report.title,
                    "old_md5": report.old_md5,
                    "new_md5": report.new_md5,
                    "playlists": report.playlists,
                    "stats": report.stats,
                    "recycled": report.recycled,
                },
            )

    def _finish_task(
        self,
        task_id: str,
        error: str = "",
        result: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task["state"] = "failed" if error else "done"
            task["current"] = ""
            if error:
                task["errors"].append(error)
            if result is not None:
                task["result"] = result

    def delete_musics(self, md5s: list[str]) -> dict[str, Any]:
        with self._lock:
            targets = [md5 for md5 in md5s or [] if md5 in self.library.musics]
            if not targets:
                return self._snapshot()
            try:
                report = source.delete_musics(targets, self.library, self.playlists, self.stats)
            except ActionError as error:
                return self._fail_message(str(error))
            if self.selection and self.selection.get("uid") in targets:
                self.selection = None
            snapshot = self._snapshot()
            snapshot["message"] = i18n.t(
                "song.deleted", count=report.removed, playlists=report.playlists
            )
            return snapshot

    # ---------- 系统 ----------

    def open_data_dir(self) -> dict[str, Any]:
        try:
            paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(str(paths.CONFIG_DIR))
            return {"ok": True}
        except OSError as error:
            return {"ok": False, "message": str(error)}

    def run_integrity(self) -> dict[str, Any]:
        with self._lock:
            return integrity.check(self.library, self.playlists, self.stats)

    def start_integrity(self, deep: bool = False) -> dict[str, Any]:
        task_id = new_uid()
        with self._lock:
            self._tasks[task_id] = {
                "state": "running",
                "kind": "integrity",
                "done": 0,
                "total": 0,
                "current": "",
                "imported": [],
                "errors": [],
                "result": None,
                "cancel": False,
            }
        thread = threading.Thread(
            target=self._run_integrity, args=(task_id, bool(deep)), name="integrity", daemon=True
        )
        thread.start()
        return {"task_id": task_id}

    def _run_integrity(self, task_id: str, deep: bool) -> None:
        def progress(done: int, total: int, name: str) -> None:
            with self._lock:
                task = self._tasks.get(task_id)
                if task is not None:
                    task["done"] = done
                    task["total"] = total
                    task["current"] = name

        def cancelled() -> bool:
            with self._lock:
                task = self._tasks.get(task_id)
                return bool(task and task.get("cancel"))

        try:
            if deep:
                report = integrity.deep_check(
                    self.library, self.playlists, self.stats, progress, cancelled
                )
            else:
                report = integrity.check(self.library, self.playlists, self.stats)
        except Exception as error:
            logger.exception("完整性检查失败")
            self._finish_task(task_id, error=str(error))
            return
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task["state"] = "cancelled" if cancelled() else "done"
            task["current"] = ""
            task["result"] = report

    def fix_issues(self, kind: str = "") -> dict[str, Any]:
        with self._lock:
            counts = integrity.fix(self.library, self.playlists, self.stats, kind)
            self.library.save()
            self.playlists.save()
            snapshot = self._snapshot()
            snapshot["fixed"] = counts
            snapshot["message"] = i18n.t("integrity.fixed", count=sum(counts.values()))
            return snapshot

    # ---------- 设置 ----------

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if isinstance(patch, dict) and patch:
                self.settings.update(patch)
            return self._snapshot()

    def set_theme(self, theme: str) -> dict[str, Any]:
        with self._lock:
            if theme in THEMES:
                self.settings.update({"common": {"theme": theme}})
            return self._snapshot()

    def browse_folder(self) -> dict[str, Any]:
        if self._window is None:
            return {"path": ""}
        try:
            result = self._window.create_file_dialog(
                webview.FOLDER_DIALOG, directory=str(paths.PROGRAM_DIR)
            )
        except Exception as error:
            logger.error("打开目录对话框失败：{}", error)
            return {"path": "", "message": str(error)}
        if not result:
            return {"path": ""}
        if isinstance(result, str):
            return {"path": result}
        return {"path": str(result[0]) if result else ""}

    def clear_all_stats(self) -> dict[str, Any]:
        with self._lock:
            removed = self.stats.clear_all()
            snapshot = self._snapshot()
            snapshot["message"] = i18n.t("settings.stats_cleared", count=removed)
            return snapshot

    def refresh_status(self) -> dict[str, Any]:
        with self._lock:
            self.status = self._system_status()
            return self._snapshot()

    def _system_status(self) -> dict[str, Any]:
        binary = ffmpeg.ffmpeg_path()
        probe = ffmpeg.ffprobe_path()
        return {
            "ffmpeg": {"available": binary is not None, "path": binary or ""},
            "ffprobe": {"available": probe is not None, "path": probe or ""},
            "data_dir": str(self.base),
            "log_dir": str(paths.LOG_DIR),
            "assets_dir": str(paths.ASSETS_DIR),
            "program_dir": str(paths.PROGRAM_DIR),
            "version": __version__,
        }

    def open_log_dir(self) -> dict[str, Any]:
        try:
            paths.LOG_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(str(paths.LOG_DIR))
            return {"ok": True}
        except OSError as error:
            return {"ok": False, "message": str(error)}
