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

from app import i18n, paths
from app.core import integrity
from app.core.importer import ImportOutcome, import_file
from app.core.library import Library
from app.core.naming import parse_filename
from app.core.playlists import PlaylistStore
from app.core.stats import StatsStore
from app.models import Author, Music, new_uid
from app.settings import SettingsStore
from app.system import theme as theme_tool

SECTIONS = ("overview", "songs", "playlists", "tags", "authors", "settings")
RECENT_LIMIT = 5
AUDIO_FILTER = ("音频文件 (*.mp3;*.m4a)",)


class ManagerApi:
    def __init__(self, config_dir: Path | None = None) -> None:
        base = config_dir or paths.CONFIG_DIR
        self.library = Library(base / "library.json")
        self.playlists = PlaylistStore(base / "playlists.json")
        self.settings = SettingsStore(base / "settings.json")
        self.stats = StatsStore(base / "stats")
        self.warnings: list[str] = []
        self.section = "overview"
        self.selection: dict[str, str] | None = None
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
            "counts": self._counts(),
            "overview": self._overview(),
            "warnings": list(self.warnings),
            "errors": [],
        }

    def _library_payload(self, missing: set[str], tag_issues: set[str]) -> dict[str, Any]:
        return {
            "authors": [author.to_dict() for author in self.library.authors.values()],
            "tag_groups": [
                group.to_dict()
                for group in sorted(self.library.tag_groups.values(), key=lambda item: item.name)
            ],
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
                "done": task["done"],
                "total": task["total"],
                "current": task["current"],
                "imported": list(task["imported"]),
                "errors": list(task["errors"]),
            }

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
            return integrity.check(self.library)
