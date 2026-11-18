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

from app import i18n, keymap, paths
from app import version as version_module
from app.core import integrity, source
from app.core.adaptation import (
    Params,
    base_percent,
    effective,
    params_from_dict,
    skip_probability,
    skip_rate,
)
from app.core.importer import commit_import, prepare_import
from app.core.library import Library
from app.core.naming import parse_filename
from app.core.playlists import PlaylistStore
from app.core.stats import StatsStore
from app.core.totals import TotalStore
from app.errors import ActionError, PlaylistCycleError
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
from app.system import ffmpeg, launcher
from app.system import theme as theme_tool
from app.system.media_server import MediaServer
from app.system.single_instance import is_running
from app.ui.manager.pomodoro_api import (
    PomodoroApiMixin,
    is_pomodoro_selection,
    make_media_hub,
    make_store,
)

SECTIONS = ("overview", "songs", "playlists", "tags", "authors", "pomodoro", "settings")
RECENT_LIMIT = 5
MAX_TASKS = 20
AUDIO_FILTER = ("音频文件 (*.mp3;*.m4a)",)
ADAPTATION_KEYS = ("window", "min_plays", "base", "skip_seconds")


def _params_dict(params: Params) -> dict[str, Any]:
    return {
        "window": params.window,
        "min_plays": params.min_plays,
        "base": params.base,
        "base_percent": base_percent(params.base),
        "skip_seconds": params.skip_seconds,
    }


def _join_names(items: list[str]) -> str:
    """列举分隔符跟着界面语言走：中文用顿号，英文用逗号。"""
    return i18n.t("list.separator").join(items)


class ManagerApi(PomodoroApiMixin):
    def __init__(
        self,
        config_dir: Path | None = None,
        first_run: bool = False,
        redirected_from: str = "",
    ) -> None:
        base = config_dir or paths.CONFIG_DIR
        self.base = base
        # 必须在 settings.load() 之前判断：它会把默认设置写到磁盘。
        self.first_run = first_run
        self.redirected_from = redirected_from
        self.library = Library(base / "library.json")
        self.playlists = PlaylistStore(base / "playlists.json")
        self.settings = SettingsStore(base / "settings.json")
        self.stats = StatsStore(base / "stats")
        self.totals = TotalStore(base / "totals.json")
        self.pomodoro = make_store(base)
        self._pomo_media = make_media_hub()
        self.warnings: list[str] = []
        self.section = "overview"
        self.selection: dict[str, str] | None = None
        self.status = self._system_status()
        self._media: MediaServer | None = None
        self._lock = threading.RLock()
        self._window = None
        self._tasks: dict[str, dict[str, Any]] = {}
        self._load()

    # ---------- 启动 ----------

    def _load(self) -> None:
        self.warnings.extend(self.settings.load())
        # 日志文件在读到设置之前就开了（默认级别），这里补上用户选的那一份。
        self.settings.apply_log_settings()
        language = self.settings.get("common", "language", default=i18n.FALLBACK_LANGUAGE)
        i18n.set_language(str(language))
        self.warnings.extend(self.library.load())
        self.warnings.extend(self.playlists.load())
        self.warnings.extend(self.pomodoro.load_locked())
        # 歌单可能在 manager 关着的时候被删掉：启动时把失效引用清掉。
        if self.pomodoro.sanitize_playlists(set(self.playlists.items)):
            self.pomodoro.save()

    def attach(self, window) -> None:
        self._window = window

    def close(self) -> None:
        try:
            with self._lock:
                self.library.save()
                self.playlists.save()
        except Exception as error:  # 关闭时保存失败不该挡住窗口退出
            logger.error("退出前保存失败：{}", error)
        if self._media is not None:
            self._media.stop()
            self._media = None
        self._pomo_media.stop()

    def _retitle(self) -> None:
        """窗口标题跟着界面语言走；老版本 pywebview 没有 set_title。"""
        if self._window is None:
            return
        try:
            self._window.set_title(i18n.t("manager.title"))
        except Exception as error:
            logger.debug("修改窗口标题失败：{}", error)

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
                # 从歌曲 / 歌单切进番茄分区时，选中项还指着别的类型；不换成总览的话
                # 前端会先画一帧空详情，再被随后那次 select_pomodoro_overview 覆盖。
                if section == "pomodoro" and not is_pomodoro_selection(self.selection.get("kind")):
                    self.selection = {"kind": "pomodoro_overview", "uid": ""}
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
            elif kind == "pomodoro" and uid in self.pomodoro.items:
                self.selection = {"kind": "pomodoro", "uid": uid}
                self.section = "pomodoro"
            elif kind == "duration_mode" and uid in self.pomodoro.duration_modes:
                self.selection = {"kind": "duration_mode", "uid": uid}
                self.section = "pomodoro"
            elif kind == "background" and uid in self.pomodoro.backgrounds:
                self.selection = {"kind": "background", "uid": uid}
                self.section = "pomodoro"
            elif kind == "ring" and uid in self.pomodoro.rings:
                self.selection = {"kind": "ring", "uid": uid}
                self.section = "pomodoro"
            elif kind == "environment" and uid in self.pomodoro.environments:
                self.selection = {"kind": "environment", "uid": uid}
                self.section = "pomodoro"
            return self._snapshot()

    def clear_selection(self) -> dict[str, Any]:
        with self._lock:
            self.selection = None
            return self._snapshot()

    # ---------- 快照 ----------

    def _snapshot(self) -> dict[str, Any]:
        """一次快照只扫一遍库。

        「文件在不在」「标签约束」「孤儿文件」「失效引用」原来各算两遍（列表一遍、
        概览一遍），几百首歌时每次点击都要多跑上千次 ``stat``。这里统一算一次再分发。
        """
        missing = set(self.library.missing_files())
        tag_issues = set(self.library.tag_violations())
        orphans = integrity.orphan_paths(self.library)
        broken = self.library.broken_references()
        return {
            "ok": True,
            "message": "",
            "section": self.section,
            "selection": self.selection,
            "language": i18n.current(),
            "languages": [
                {"code": code, "name": name} for code, name in i18n.available_languages()
            ],
            "theme": theme_tool.resolve(str(self.settings.get("common", "theme", default="light"))),
            "version": version_module.version(),
            "first_run": self.first_run,
            "redirected_from": self.redirected_from,
            "data_dir": str(paths.DATA_DIR),
            "data_dir_next": str(paths.pending_data_dir() or ""),
            "data_dir_default": str(paths.DATA_DIR_DEFAULT),
            "library": self._library_payload(missing, tag_issues),
            "playlists": self._playlist_payload(),
            "settings": self.settings.data,
            "keys": {
                "actions": {group: list(keymap.DEFAULTS[group]) for group in keymap.GROUPS},
                "defaults": {group: dict(keymap.DEFAULTS[group]) for group in keymap.GROUPS},
            },
            "status": self.status,
            "counts": self._counts(),
            "overview": self._overview(missing, tag_issues, orphans, broken),
            "pomodoro": self._pomodoro_payload(),
            "warnings": list(self.warnings),
            "errors": [],
        }

    def _reference_counts(self) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
        """一次遍历算出标签、标签组、作者各被多少首歌引用。

        原来是「每个作者扫一遍全部歌曲」，作者上百个就是几十万次比较；
        改成遍历歌曲、给计数加一，代价与作者数量无关。
        """
        group_of = {
            tag.uid: group.uid for group in self.library.tag_groups.values() for tag in group.tags
        }
        tag_counts: dict[str, int] = {}
        group_counts: dict[str, int] = {}
        author_counts: dict[str, int] = {}
        for music in self.library.musics.values():
            for uid in music.tags:
                tag_counts[uid] = tag_counts.get(uid, 0) + 1
            for uid in music.authors:
                author_counts[uid] = author_counts.get(uid, 0) + 1
            for group_uid in {group_of[uid] for uid in music.tags if uid in group_of}:
                group_counts[group_uid] = group_counts.get(group_uid, 0) + 1
        return tag_counts, group_counts, author_counts

    def _library_payload(self, missing: set[str], tag_issues: set[str]) -> dict[str, Any]:
        tag_counts, group_counts, author_counts = self._reference_counts()
        # 标签组的顺序就是文件里的顺序：用户拖出来的顺序要能留住。
        tag_groups: list[dict[str, Any]] = []
        for group in self.library.tag_groups.values():
            payload = group.to_dict()
            payload["count"] = group_counts.get(group.uid, 0)
            for tag in payload["tags"]:
                tag["count"] = tag_counts.get(tag["uid"], 0)
            tag_groups.append(payload)

        # 作者不提供手动排序，展示时一律按名称。
        authors: list[dict[str, Any]] = []
        for author in sorted(self.library.authors.values(), key=lambda item: item.name.casefold()):
            payload = author.to_dict()
            payload["count"] = author_counts.get(author.uid, 0)
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
        payload["authors_text"] = _join_names(self.library.music_authors(music))
        payload["missing"] = music.md5 in missing
        payload["tag_issue"] = music.md5 in tag_issues
        return payload

    def _sorted_musics(self) -> list[Music]:
        return sorted(self.library.musics.values(), key=lambda item: item.title.lower())

    def _playlist_payload(self) -> list[dict[str, Any]]:
        # 顺序即文件里的数组顺序：歌单列表可以拖拽排序，排序结果要能留住。
        result: list[dict[str, Any]] = []
        for playlist in self.playlists.all():
            payload = playlist.to_dict()
            payload["title"] = playlist.name or i18n.t("overview.default_playlist")
            payload["error"] = ""
            payload["error_detail"] = None
            try:
                content = self.playlists.resolve(playlist.uid, self.library)
                payload["count"] = len(content.md5s)
            except PlaylistCycleError as error:  # 循环引用不该让整个快照失败
                payload["count"] = 0
                payload["error"] = str(error)
                payload["error_detail"] = self._cycle_detail(error)
            except Exception as error:
                payload["count"] = 0
                payload["error"] = str(error)
                payload["error_detail"] = {"kind": "error", "chain": [], "text": str(error)}
            result.append(payload)
        return result

    def _playlist_title(self, uid: str) -> str:
        playlist = self.playlists.get(uid)
        if playlist is None:
            return uid[:8]
        return playlist.name or i18n.t("overview.default_playlist")

    def _cycle_detail(self, error: PlaylistCycleError) -> dict[str, Any]:
        """把循环链里的 uid 换成歌单名，界面直接画成卡片。"""
        chain = [self._playlist_title(uid) for uid in error.chain]
        return {"kind": "cycle", "chain": chain, "text": " → ".join(chain) or str(error)}

    def _cycle_message(self, error: PlaylistCycleError) -> str:
        """给弹窗用的一句话；链里的 uid 换成歌单名。"""
        chain = " → ".join(self._playlist_title(uid) for uid in error.chain)
        return i18n.t("playlist.cycle_message", chain=chain or str(error))

    def _counts(self) -> dict[str, int]:
        counts = self.library.counts()
        counts["playlists"] = len(self.playlists.items)
        return counts

    def _overview(
        self,
        missing: set[str] | None = None,
        tag_issues: set[str] | None = None,
        orphans: list | None = None,
        broken: list[str] | None = None,
    ) -> dict[str, Any]:
        now = int(time.time())
        musics = sorted(
            self.library.musics.values(), key=lambda item: item.created_at, reverse=True
        )
        recent_imported = [
            {
                "kind": "music",
                "md5": music.md5,
                "title": music.title,
                "subtitle": _join_names(self.library.music_authors(music)),
                "at": music.created_at,
            }
            for music in musics[:RECENT_LIMIT]
        ]

        edited: list[dict[str, Any]] = [
            {
                "kind": "music",
                "md5": music.md5,
                "title": music.title,
                "subtitle": _join_names(self.library.music_authors(music)),
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

        if missing is None:
            missing = set(self.library.missing_files())
        if tag_issues is None:
            tag_issues = set(self.library.tag_violations())
        if orphans is None:
            orphans = integrity.orphan_paths(self.library)
        if broken is None:
            broken = self.library.broken_references()

        issues: list[dict[str, Any]] = []
        if tag_issues:
            issues.append({"kind": "missing_tag", "count": len(tag_issues)})
        if missing:
            issues.append({"kind": "missing_file", "count": len(missing)})
        if orphans:
            issues.append({"kind": "orphan_file", "count": len(orphans)})
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
                names = _join_names([music.title for music in songs[:3]])
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

    def reorder_tags(self, group_uid: str, uids: list[str]) -> dict[str, Any]:
        """组里的小标签按拖出来的顺序落盘；没提到的留在末尾。"""
        with self._lock:
            group = self.library.tag_groups.get(group_uid)
            if group is None:
                return self._snapshot()
            remaining = {tag.uid: tag for tag in group.tags}
            tags: list[Tag] = []
            for uid in uids or []:
                tag = remaining.pop(str(uid), None)
                if tag is not None:
                    tags.append(tag)
            tags.extend(remaining.values())
            if [tag.uid for tag in tags] != [tag.uid for tag in group.tags]:
                group.tags = tags
                self.library.save()
            return self._snapshot()

    def reorder_tag_groups(self, uids: list[str]) -> dict[str, Any]:
        with self._lock:
            self.library.reorder_tag_groups([str(uid) for uid in uids or []])
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
                names = _join_names([music.title for music in songs[:3]])
                return self._fail("author.referenced", count=len(songs), names=names)
            for music in songs:
                music.authors = [item for item in music.authors if item != uid]
                self._touch(music)
            self.library.remove_author(uid)
            self.library.save()
            if self.selection and self.selection.get("uid") == uid:
                self.selection = None
            return self._snapshot()

    def delete_empty_authors(self) -> dict[str, Any]:
        """一键清掉没有任何作品归属的作者。"""
        with self._lock:
            empty = [uid for uid in self.library.authors if not self.library.author_songs(uid)]
            for uid in empty:
                self.library.remove_author(uid)
            if empty:
                self.library.save()
                if self.selection and self.selection.get("uid") in empty:
                    self.selection = None
            snapshot = self._snapshot()
            snapshot["message"] = i18n.t("author.cleaned", count=len(empty))
            return snapshot

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
                snapshot["message"] = i18n.t("playlist.referenced", names=_join_names(referrers))
                return snapshot
            self.playlists.remove(uid)
            self.playlists.save()
            self.stats.remove(uid)
            self.pomodoro.drop_playlist(uid)
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
                    names.append(self._playlist_title(playlist.uid))
                    break
        return names

    def reorder_playlists(self, uids: list[str]) -> dict[str, Any]:
        """歌单列表按拖出来的顺序落盘；播放器也照这个顺序展示。"""
        with self._lock:
            self.playlists.reorder([str(uid) for uid in uids or []])
            self.playlists.save()
            return self._snapshot()

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
                # 删掉最后一条时补回「包含 · 全部歌曲」，内存状态与下次加载一致。
                playlist.normalize()
                self.playlists.touch(uid)
                self.playlists.save()
            return self._snapshot()

    def reorder_filters(self, uid: str, order: list[int]) -> dict[str, Any]:
        """条件行按拖出来的顺序落盘；``order`` 是拖动前的下标顺序。

        没出现在 ``order`` 里的条件留在末尾，不会被丢掉——界面只传可见的那些。
        """
        with self._lock:
            playlist = self.playlists.get(uid)
            if playlist is None or playlist.kind != "filter":
                return self._snapshot()
            current = list(playlist.filters)
            picked: list[Filter] = []
            used: set[int] = set()
            for raw in order or []:
                try:
                    index = int(raw)
                except (TypeError, ValueError):
                    continue
                if 0 <= index < len(current) and index not in used:
                    used.add(index)
                    picked.append(current[index])
            for index, condition in enumerate(current):
                if index not in used:
                    picked.append(condition)
            if any(before is not after for before, after in zip(picked, current, strict=True)):
                playlist.filters = picked
                self.playlists.touch(uid)
                self.playlists.save()
            return self._snapshot()

    def get_playlist_songs(self, uid: str) -> dict[str, Any]:
        with self._lock:
            try:
                content = self.playlists.resolve(uid, self.library)
            except PlaylistCycleError as error:
                return {"ok": False, "message": self._cycle_message(error), "items": []}
            except Exception as error:
                logger.error("解析歌单失败：{}（{}）", uid, error)
                return {"ok": False, "message": f"解析歌单失败：{error}", "items": []}
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
            except PlaylistCycleError as error:
                return {"ok": False, "message": self._cycle_message(error), "rows": []}
            except Exception as error:
                logger.error("解析歌单失败：{}（{}）", uid, error)
                return {"ok": False, "message": f"解析歌单失败：{error}", "rows": []}

            summary = self.stats.summary(uid)
            totals = self.totals.summary()
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
                        "full_plays": int(item.get("full_plays", 0) or 0),
                        # 总播放次数与自适应无关：换个歌单看也是同一个数。
                        "total_plays": int(totals.get(md5, 0)),
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
        """歌曲详情用：只看「默认歌单」这一套配置与记录。

        自适应是按歌单各自独立配置的，同一首歌在不同歌单里的记录互不相干；
        歌曲页没有「哪个歌单」的上下文，约定用默认歌单的数据。
        """
        with self._lock:
            if md5 not in self.library.musics:
                return {"ok": False}
            playlist = self.playlists.default()
            defaults = self._adaptation_defaults()
            params = effective(playlist.adaptation, defaults)
            try:
                content = self.playlists.resolve(playlist.uid, self.library)
                in_playlist = md5 in content.md5s
            except Exception:
                in_playlist = False
            summary = self.stats.summary(playlist.uid).get(md5) or {}
            records = str(summary.get("records", ""))
            return {
                "ok": True,
                "playlist": {
                    "uid": playlist.uid,
                    "title": playlist.name or i18n.t("overview.default_playlist"),
                    "enabled": playlist.adaptation.enabled,
                },
                "in_playlist": in_playlist,
                "params": _params_dict(params),
                "total": len(records),
                "skips": records.count("1"),
                "rate": skip_rate(records),
                "auto_skipped": int(summary.get("auto_skipped", 0) or 0),
                "full_plays": int(summary.get("full_plays", 0) or 0),
                # 总播放次数是全库一份，与这首歌在不在默认歌单里无关。
                "total_plays": self.totals.get(md5),
                "probability": skip_probability(records, params),
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

    def _start_dir(self) -> str:
        return str(paths.resolve_user_path(str(self.settings.get("import", "dir", default=""))))

    def _ask_paths(self, *, multiple: bool) -> list[str]:
        """文件选择对话框；失败只记日志，返回空列表。

        老版本 pywebview 有时返回 ``str``，有时返回 ``list``，统一成列表。
        """
        if self._window is None:
            return []
        try:
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                directory=self._start_dir(),
                allow_multiple=multiple,
                file_types=AUDIO_FILTER,
            )
        except Exception as error:
            logger.error("打开文件对话框失败：{}", error)
            return []
        if not result:
            return []
        if isinstance(result, str):
            return [result]
        return [str(item) for item in result]

    def browse_import(self) -> dict[str, Any]:
        return {"paths": self._ask_paths(multiple=True)}

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

    def _register_task(self, payload: dict[str, Any]) -> str:
        """登记一个任务并清掉过期的旧任务，任务表不会无限长。"""
        task_id = new_uid()
        with self._lock:
            self._tasks[task_id] = payload
            stale = [key for key, item in self._tasks.items() if item["state"] != "running"]
            for key in stale[: max(0, len(self._tasks) - MAX_TASKS)]:
                del self._tasks[key]
        return task_id

    def _task_patch(self, task_id: str, **fields: Any) -> dict[str, Any] | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task.update(fields)
            return task

    def start_import(self, items: list[Any], clean: bool | None = None) -> dict[str, Any]:
        # ``clean`` 保留在签名里只为兼容旧调用；音乐导入现在一律清元数据。
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

        task_id = self._register_task(
            {
                "state": "running",
                "done": 0,
                "total": len(normalized),
                "current": "",
                "imported": [],
                "errors": [],
            }
        )
        thread = threading.Thread(
            target=self._run_import, args=(task_id, normalized), name="import", daemon=True
        )
        thread.start()
        return {"task_id": task_id}

    def _run_import(self, task_id: str, items: list[dict[str, Any]]) -> None:
        """逐条导入。

        清洗、算 MD5、读时长都在锁外做——这些是秒级的；只有「落盘 + 写进内存库」
        这一小段在锁内。否则导入期间界面的每一次快照都会被锁住，而导入线程
        直接改 ``library.musics`` 又会让别的线程撞上「字典在迭代时被改变」。

        音乐导入一律清元数据：清洗后的字节决定 MD5，跳过清洗会让同一个文件在
        不同机器上算出不同的身份。
        """
        for index, entry in enumerate(items, start=1):
            path = Path(entry["path"])
            if self._task_patch(task_id, current=path.name) is None:
                return

            try:
                prepared = prepare_import(path, True)
            except Exception as error:  # 单个文件失败不打断整批
                logger.warning("导入准备失败：{}（{}）", path, error)
                self._record_import_error(task_id, f"{path.name}：{error}", index)
                continue

            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    prepared.discard()
                    return
                try:
                    outcome = commit_import(
                        prepared, self.library, entry.get("title"), entry.get("authors")
                    )
                except Exception as error:
                    logger.exception("导入提交失败：{}", path)
                    task["errors"].append(f"{path.name}：导入失败（{error}）")
                else:
                    if outcome.error:
                        task["errors"].append(f"{path.name}：{outcome.error}")
                    elif outcome.duplicate:
                        existing = self.library.musics.get(prepared.md5)
                        key = "import.duplicate" if existing else "import.duplicate_unknown"
                        task["errors"].append(
                            f"{path.name}：" + i18n.t(key, title=existing.title if existing else "")
                        )
                    else:
                        task["imported"].append(outcome.music.md5)
                        self.library.save()
                task["done"] = index

        self._task_patch(task_id, state="done", current="")

    def _record_import_error(self, task_id: str, message: str, index: int) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task["errors"].append(message)
                task["done"] = index

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
        picked = self._ask_paths(multiple=False)
        return {"path": picked[0] if picked else ""}

    def _adaptation_defaults(self) -> Params:
        return params_from_dict(self.settings.get("common", "adaptation", default={}))

    def start_replace_source(self, md5: str, path: str) -> dict[str, Any]:
        with self._lock:
            if md5 not in self.library.musics:
                return {"task_id": ""}
        task_id = self._register_task(
            {
                "state": "running",
                "kind": "replace",
                "done": 0,
                "total": 1,
                "current": "",
                "imported": [],
                "errors": [],
                "result": None,
            }
        )
        thread = threading.Thread(
            target=self._run_replace, args=(task_id, md5, path), name="replace", daemon=True
        )
        thread.start()
        return {"task_id": task_id}

    def _run_replace(self, task_id: str, md5: str, path: str) -> None:
        try:
            prepared = source.prepare_replacement(Path(path), True)
        except ActionError as error:
            self._finish_task(task_id, error=str(error))
            return
        except Exception as error:  # 未预料的失败也要让界面能退出进度框
            logger.exception("换源准备失败")
            self._finish_task(task_id, error=f"换源失败：{error}")
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
                    self.totals,
                )
            except ActionError as error:
                self._finish_task(task_id, error=str(error))
                return
            except Exception as error:
                logger.exception("换源失败")
                self._finish_task(task_id, error=f"换源失败：{error}")
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
                report = source.delete_musics(
                    targets, self.library, self.playlists, self.stats, self.totals
                )
            except ActionError as error:
                return self._fail_message(str(error))
            if self.selection and self.selection.get("uid") in targets:
                self.selection = None
            snapshot = self._snapshot()
            snapshot["message"] = i18n.t(
                "song.deleted", count=report.removed, playlists=report.playlists
            )
            return snapshot

    # ---------- 启动其他程序 ----------

    def launch_player(self) -> dict[str, Any]:
        if is_running("MusicPlayerPlayer"):
            return {"ok": False, "message": i18n.t("launch.player_running")}
        if not launcher.spawn(paths.PLAYER_ENTRY):
            return {"ok": False, "message": i18n.t("launch.failed")}
        return {"ok": True}

    def launch_simple(self) -> dict[str, Any]:
        if is_running("MusicPlayerSimple"):
            return {"ok": False, "message": i18n.t("launch.simple_running")}
        if not launcher.spawn(paths.SIMPLE_ENTRY, console=True):
            return {"ok": False, "message": i18n.t("launch.failed")}
        return {"ok": True}

    # ---------- 试听 ----------

    def audition_url(self, md5: str) -> dict[str, Any]:
        """给底部试听条一个能 Range 的地址；播放控制都在网页里做。"""
        with self._lock:
            music = self.library.musics.get(md5)
            if music is None:
                return {"ok": False}
            path = paths.music_path(md5, music.ext)
            if not path.exists():
                return {"ok": False, "message": i18n.t("song.missing_file")}
            if self._media is None:
                self._media = MediaServer(paths.MUSIC_DIR)
            return {
                "ok": True,
                "url": self._media.url(path.name),
                "title": music.title,
                "duration_ms": music.duration_ms,
            }

    # ---------- 系统 ----------

    def _open_dir(self, path: Path) -> dict[str, Any]:
        try:
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))
            return {"ok": True}
        except (OSError, AttributeError) as error:  # 非 Windows 上没有 os.startfile
            logger.error("打开目录失败：{}（{}）", path, error)
            return {"ok": False, "message": f"无法打开目录：{error}"}

    def open_data_dir(self) -> dict[str, Any]:
        return self._open_dir(paths.CONFIG_DIR)

    def open_log_dir(self) -> dict[str, Any]:
        return self._open_dir(paths.LOG_DIR)

    def run_integrity(self) -> dict[str, Any]:
        with self._lock:
            return integrity.check(self.library, self.playlists, self.stats)

    def start_integrity(self, deep: bool = False) -> dict[str, Any]:
        task_id = self._register_task(
            {
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
        )
        thread = threading.Thread(
            target=self._run_integrity, args=(task_id, bool(deep)), name="integrity", daemon=True
        )
        thread.start()
        return {"task_id": task_id}

    def _run_integrity(self, task_id: str, deep: bool) -> None:
        def progress(done: int, total: int, name: str) -> None:
            self._task_patch(task_id, done=done, total=total, current=name)

        def cancelled() -> bool:
            with self._lock:
                task = self._tasks.get(task_id)
                return bool(task and task.get("cancel"))

        try:
            if deep:
                # 深检要遍历全部歌曲重算 MD5，期间导入线程可能正在加歌。
                # 用一份副本做检查：结果对应一个一致的时间点，也不会撞上迭代中修改。
                with self._lock:
                    library = self.library.clone()
                report = integrity.deep_check(
                    library, self.playlists, self.stats, progress, cancelled
                )
            else:
                with self._lock:
                    report = integrity.check(self.library, self.playlists, self.stats)
        except Exception as error:
            logger.exception("完整性检查失败")
            self._finish_task(task_id, error=f"完整性检查失败：{error}")
            return
        self._task_patch(
            task_id,
            state="cancelled" if cancelled() else "done",
            current="",
            result=report,
        )

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
                self._sync_language()
                # 只有动了日志三件套才重配日志：其余设置不该顺手把文件重开一遍。
                common_patch = patch.get("common")
                if isinstance(common_patch, dict) and any(
                    str(key).startswith("log_") for key in common_patch
                ):
                    self.settings.apply_log_settings()
            return self._snapshot()

    def set_shortcut(self, group: object, action: object, spec: object) -> dict[str, Any]:
        """改一个快捷键。

        走这条路而不是直接 ``update_settings``：认不出来的组合、控制台读不到的
        组合、和同页另一个动作撞车的组合都在这里拦下，界面按 ``reason`` 给提示。
        成功时返回完整快照，并额外带一个 ``shortcut`` 说明改成了什么。
        """
        with self._lock:
            if group not in keymap.GROUPS or not isinstance(action, str):
                return {"ok": False, "reason": "invalid"}
            table = self.settings.get(group, "keys", default={})
            if not isinstance(table, dict) or action not in table:
                return {"ok": False, "reason": "invalid"}
            wanted = keymap.normalize(spec)
            if wanted is None:
                return {"ok": False, "reason": "invalid"}
            if group == "simple" and not keymap.console_supported(wanted):
                return {"ok": False, "reason": "unsupported"}
            for other, current in table.items():
                if other != action and current == wanted:
                    return {"ok": False, "reason": "conflict", "action": other}

            self.settings.update({group: {"keys": {action: wanted}}})
            snapshot = self._snapshot()
            snapshot["shortcut"] = {"group": group, "action": action, "spec": wanted}
            return snapshot

    def _sync_language(self) -> None:
        """设置里的语言变了就立刻生效：文案、窗口标题一起换。"""
        language = str(self.settings.get("common", "language", default=i18n.FALLBACK_LANGUAGE))
        if language == i18n.current():
            return
        if i18n.set_language(language) == language:
            self._retitle()

    def set_language(self, language: str) -> dict[str, Any]:
        with self._lock:
            if language in dict(i18n.available_languages()):
                self.settings.update({"common": {"language": language}})
                i18n.set_language(language)
                self._retitle()
            return self._snapshot()

    def preview_language(self, language: str) -> dict[str, Any]:
        """首次运行的语言下拉框：只换内存里的语言，不落盘。

        落盘会让「第一次运行」的判据（settings.json 是否存在）提前成立，
        用户中途关掉窗口就再也看不到语言选择。
        """
        with self._lock:
            if language in dict(i18n.available_languages()):
                i18n.set_language(language)
                self._retitle()
            return {"ok": True, "language": i18n.current(), "strings": i18n.strings()}

    def set_theme(self, theme: str) -> dict[str, Any]:
        with self._lock:
            if theme in THEMES:
                self.settings.update({"common": {"theme": theme}})
            return self._snapshot()

    # ---------- 关于 ----------

    def complete_first_run(self, language: str) -> dict[str, Any]:
        """首次启动选完语言：语言落盘，外观按系统偏好定一次。"""
        with self._lock:
            self.settings.update({"common": {"language": i18n.set_language(str(language))}})
            self.settings.update({"common": {"theme": theme_tool.system_theme()}})
            i18n.set_language(str(language))
            self.first_run = False
            self._retitle()
            return self._snapshot()

    def get_readme(self) -> dict[str, Any]:
        """当前语言的使用手册；没有这一份就退回英文。"""
        language = i18n.current()
        path = paths.PROGRAM_DIR / "docs" / "readme" / f"{language}.md"
        if not path.is_file():
            language = i18n.FALLBACK_LANGUAGE
            path = paths.PROGRAM_DIR / "docs" / "readme" / f"{language}.md"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        return {"language": language, "markdown": text}

    def reset_settings(self) -> dict[str, Any]:
        """恢复出厂设置。语言与外观一起重置，界面随后整体重绘。"""
        with self._lock:
            self.settings.reset()
            i18n.set_language(
                str(self.settings.get("common", "language", default=i18n.FALLBACK_LANGUAGE))
            )
            self._retitle()
            snapshot = self._snapshot()
            snapshot["message"] = i18n.t("about.reset_done")
            return snapshot

    def set_data_dir(self, raw: str) -> dict[str, Any]:
        """记下新的数据目录：补项目代号，下次启动把文件搬过去。"""
        with self._lock:
            try:
                target = paths.request_data_dir(str(raw), base=paths.DATA_DIR)
            except OSError as error:
                snapshot = self._snapshot()
                snapshot["ok"] = False
                snapshot["message"] = i18n.t("about.data_dir_failed", error=error)
                return snapshot
            snapshot = self._snapshot()
            snapshot["message"] = (
                i18n.t("about.data_dir_saved", path=target)
                if snapshot["data_dir_next"]
                else i18n.t("about.data_dir_same")
            )
            return snapshot

    def reset_data_dir(self) -> dict[str, Any]:
        """把数据目录恢复成默认位置。"""
        return self.set_data_dir(str(paths.DATA_DIR_DEFAULT))

    def browse_folder(self) -> dict[str, Any]:
        if self._window is None:
            return {"path": ""}
        try:
            result = self._window.create_file_dialog(
                webview.FOLDER_DIALOG, directory=str(paths.PROGRAM_DIR)
            )
        except Exception as error:
            logger.error("打开目录对话框失败：{}", error)
            return {"path": ""}
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
            "version": version_module.version(),
        }
