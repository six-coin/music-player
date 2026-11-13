"""播放器的 JS 桥。

负责：加载库、歌单、设置与统计，把网页调用翻译成 ``PlayerSession`` 的操作，
组装快照，按计划 §6 写盘。队列规则不在这里——它只认识「下一首是谁」。
"""

from __future__ import annotations

import random
import threading
import time
from pathlib import Path
from typing import Any

from loguru import logger

from app import i18n, paths
from app.core import adaptation
from app.core.library import Library
from app.core.player_session import (
    ALL_SKIPPED,
    CYCLE,
    FAILED,
    MISSING,
    Hooks,
    Load,
    PlayerSession,
    Stop,
)
from app.core.playlists import PlaylistStore
from app.core.stats import SongStats, StatsStore
from app.errors import AppError, ConfigError
from app.models import Music, Playlist
from app.settings import SettingsStore
from app.system import atomic, launcher
from app.system import theme as theme_tool
from app.system.media_server import MediaServer

STATE_VERSION = 1
PICK_LIMIT = 200
POSITION_SAVE_SECONDS = 10
DEFAULT_SIZE = (960, 620)
MIN_SIZE = (760, 480)


def _milliseconds(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


def _clamp_size(value: object, low: int, fallback: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return fallback
    return max(low, value)


class PlayerApi:
    def __init__(self, config_dir: Path | None = None) -> None:
        base = config_dir or paths.CONFIG_DIR
        self.base = base
        self.settings = SettingsStore(base / "settings.json")
        self.library = Library(base / "library.json")
        self.playlists = PlaylistStore(base / "playlists.json")
        self.stats = StatsStore(base / "stats")
        self.state_path = base / "player.json"

        self.warnings: list[str] = []
        self._lock = threading.RLock()
        self._window = None
        self._media: MediaServer | None = None
        self._rng = random.Random()
        self._records: dict[str, SongStats] = {}
        self._records_uid = ""
        self._failed: set[str] = set()
        self._counts: dict[str, int] = {}
        self._queue_visible = True
        self._window_size = DEFAULT_SIZE
        self._last_save = time.monotonic()

        self._load()
        self.session = PlayerSession(
            self.library,
            self.playlists,
            mode=str(self.settings.get("player", "order", default="shuffle")),
            rng=self._rng,
            hooks=Hooks(self._available, self._should_skip, self._on_auto_skip),
        )
        self._restore()

    # ---------- 启动 ----------

    def _load(self) -> None:
        self._backup_broken_settings()
        self.warnings.extend(self.settings.load())
        language = self.settings.get("common", "language", default=i18n.DEFAULT_LANGUAGE)
        i18n.set_language(str(language))
        self.warnings.extend(self.library.load())
        self.warnings.extend(self.playlists.load())
        self._load_state()
        self._counts = self._playlist_counts()

    def _backup_broken_settings(self) -> None:
        path = self.settings.path
        if not path.exists():
            return
        try:
            atomic.read_json(path)
            return
        except ConfigError:
            pass
        backup = Path(f"{path}.bad")
        if backup.exists():
            backup = Path(f"{path}.bad-{int(time.time())}")
        try:
            path.replace(backup)
        except OSError:
            logger.exception("备份损坏的设置文件失败")
            return
        self.warnings.append(f"设置文件已损坏，备份为 {backup.name}，本次使用默认值")
        logger.warning("设置文件已损坏，备份为 {}", backup.name)

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            raw = atomic.read_json(self.state_path)
        except ConfigError:
            return
        if not isinstance(raw, dict):
            return
        self._queue_visible = bool(raw.get("queue_visible", True))
        window = raw.get("window")
        if isinstance(window, dict):
            self._window_size = (
                _clamp_size(window.get("width"), MIN_SIZE[0], DEFAULT_SIZE[0]),
                _clamp_size(window.get("height"), MIN_SIZE[1], DEFAULT_SIZE[1]),
            )

    def window_size(self) -> tuple[int, int]:
        return self._window_size

    def attach(self, window) -> None:
        self._window = window

    def close(self) -> None:
        try:
            with self._lock:
                self._save_progress()
                self._save_state(self._window)
        except Exception:  # 退出路径上的保存失败不阻断关窗
            logger.exception("退出前保存失败")
        media = self._media
        self._media = None
        if media is not None:
            try:
                media.stop()
            except Exception:
                logger.exception("停止媒体服务失败")

    # ---------- 读取 ----------

    def get_strings(self) -> dict[str, str]:
        return i18n.strings()

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            self._reload_records()
            return self._snapshot()

    def list_songs(self, query: object = "") -> dict[str, Any]:
        with self._lock:
            text = query.strip().casefold() if isinstance(query, str) else ""
            in_playlist = set(self.session.order)
            items: list[dict[str, Any]] = []
            musics = sorted(self.library.musics.values(), key=lambda item: item.title.casefold())
            for music in musics:
                authors = self._authors_text(music)
                if text and not self._matches(music, authors, text):
                    continue
                items.append(
                    {
                        "md5": music.md5,
                        "title": music.title,
                        "authors": authors,
                        "in_playlist": music.md5 in in_playlist,
                    }
                )
                if len(items) >= PICK_LIMIT:
                    break
            return {"items": items}

    # ---------- 歌单与切歌 ----------

    def select_playlist(self, uid: object) -> dict[str, Any]:
        with self._lock:
            if not isinstance(uid, str) or not uid:
                return self._snapshot()
            if uid == self.session.playlist_uid and self.session.current_md5 is not None:
                return self._snapshot()  # 点已选中的歌单不重置；没歌可播时允许重点重试
            self._records = {}
            self._records_uid = ""
            self.session.load_playlist(uid, autoplay=True)
            self._after_change()
            return self._snapshot()

    def next_track(self, md5: object = "", played_ms: object = 0) -> dict[str, Any]:
        with self._lock:
            self._record_skip(md5, played_ms)
            self.session.next()
            self._after_change()
            return self._snapshot()

    def prev_track(self, md5: object = "", played_ms: object = 0) -> dict[str, Any]:
        with self._lock:
            self.session.previous()
            self._after_change()
            return self._snapshot()

    def jump_to(self, md5: object, played_ms: object = 0) -> dict[str, Any]:
        with self._lock:
            if not isinstance(md5, str):
                return self._snapshot()
            self.session.jump(md5)
            self._after_change()
            return self._snapshot()

    def track_ended(self, md5: object = "", played_ms: object = 0) -> dict[str, Any]:
        with self._lock:
            current = self.session.current_md5
            if not isinstance(md5, str) or md5 != current:
                return self._snapshot()  # 过期事件：已经切走了，不再前进
            self._record(md5, _milliseconds(played_ms), natural=True)
            self.session.on_ended()
            self._after_change()
            return self._snapshot()

    def track_failed(self, md5: object = "", reason: object = "") -> dict[str, Any]:
        with self._lock:
            current = self.session.current_md5
            if isinstance(md5, str) and md5 == current:
                self._failed.add(md5)
                logger.warning("播放失败：{}（{}）", md5, reason)
                self.session.note(FAILED, md5)
                self.session.on_failed(md5)
                self._after_change()
            return self._snapshot()

    # ---------- 模式 ----------

    def set_mode(self, mode: object) -> dict[str, Any]:
        with self._lock:
            if isinstance(mode, str) and self.session.set_mode(mode):
                self.settings.patch_player({"order": self.session.mode})
                self._after_change()
            return self._snapshot()

    def pick_loop_song(self, md5: object, played_ms: object = 0) -> dict[str, Any]:
        with self._lock:
            if not isinstance(md5, str):
                return self._snapshot()
            if self.session.pick_loop_song(md5):
                self._after_change()
            return self._snapshot()

    # ---------- 播放状态 ----------

    def set_playing(self, on: object) -> dict[str, Any]:
        with self._lock:
            self.session.set_playing(bool(on))
            if not on:
                self._save_progress()
            return {"ok": True}

    def report_position(self, position_ms: object) -> dict[str, Any]:
        with self._lock:
            self.session.set_position(_milliseconds(position_ms))
            now = time.monotonic()
            if now - self._last_save >= POSITION_SAVE_SECONDS:
                self._save_progress()
                self._last_save = now
            return {"ok": True}

    def set_volume(self, value: object) -> dict[str, Any]:
        with self._lock:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return {"ok": False}
            volume = float(value)
            if volume != volume:  # NaN
                return {"ok": False}
            self.settings.patch_player({"volume": round(min(1.0, max(0.0, volume)), 3)})
            return {"ok": True}

    def set_queue_visible(self, on: object) -> dict[str, Any]:
        with self._lock:
            self._queue_visible = bool(on)
            self._save_state()
            return self._snapshot()

    # ---------- 系统 ----------

    def open_manager(self) -> dict[str, Any]:
        return {"ok": launcher.spawn(paths.MANAGER_ENTRY)}

    # ---------- 快照 ----------

    def _snapshot(self) -> dict[str, Any]:
        state = self.session.snapshot()
        current = state["current_md5"]
        items = [self._queue_item(item) for item in state["queue"]]
        pinned = state["pinned"]
        return {
            "ok": True,
            "language": i18n.current(),
            "theme": theme_tool.resolve(
                str(self.settings.get("common", "theme", default="system"))
            ),
            "theme_source": str(self.settings.get("common", "theme", default="system")),
            "mode": state["mode"],
            "playlist_uid": state["playlist_uid"],
            "playlists": [
                {
                    "uid": playlist.uid,
                    "title": self._playlist_title(playlist),
                    "count": self._counts.get(playlist.uid, 0),
                    "active": playlist.uid == state["playlist_uid"],
                }
                for playlist in self.playlists.all()
            ],
            "track": self._track_payload(current, state["position_ms"]),
            "transport": {
                "playing": state["playing"],
                "can_prev": state["can_prev"],
                "can_next": state["can_next"],
            },
            "queue": {
                "visible": self._queue_visible,
                "items": items,
                "current_md5": current,
                "pinned": self._title(pinned) if isinstance(pinned, str) else None,
            },
            "volume": float(self.settings.get("player", "volume", default=0.8)),
            "empty": self._empty_value(state["empty"]),
            "notice": self._notice_payload(state["notice"]),
            "warnings": list(self.warnings),
            "command": self._command_payload(state["command"]),
        }

    def _track_payload(self, md5: object, position_ms: object) -> dict[str, Any] | None:
        if not isinstance(md5, str):
            return None
        music = self.library.find_music(md5)
        if music is None:
            return None
        return {
            "md5": md5,
            "title": music.title,
            "authors": self._authors_text(music),
            "duration_ms": music.duration_ms,
            "position_ms": _milliseconds(position_ms),
            "missing": not self._available(md5),
        }

    def _queue_item(self, item: dict[str, str]) -> dict[str, Any]:
        md5 = item["md5"]
        music = self.library.find_music(md5)
        return {
            "md5": md5,
            "title": music.title if music else md5[:8],
            "missing": not self._available(md5),
            "state": item["state"],
        }

    def _command_payload(self, command: object) -> dict[str, Any] | None:
        if isinstance(command, Stop):
            return {"seq": command.seq, "kind": "stop"}
        if isinstance(command, Load):
            music = self.library.find_music(command.md5)
            url = ""
            if music is not None and self._available(command.md5):
                url = self._media_url(command.md5, music.ext)
            return {
                "seq": command.seq,
                "kind": "load",
                "md5": command.md5,
                "url": url,
                "reason": "" if url else "media",
                "position_ms": command.position_ms,
                "autoplay": command.autoplay,
            }
        return None

    def _notice_payload(self, notice: object) -> dict[str, Any] | None:
        kind = getattr(notice, "kind", "")
        seq = getattr(notice, "seq", 0)
        md5 = getattr(notice, "md5", "")
        count = getattr(notice, "count", 0)
        title = self._title(md5) if md5 else ""
        if kind == MISSING:
            if count > 1:
                text = i18n.t("player.notice.missing_many", title=title, count=count)
            else:
                text = i18n.t("player.notice.missing", title=title)
        elif kind == FAILED:
            text = i18n.t("player.notice.failed", title=title)
        elif kind == CYCLE:
            text = i18n.t("player.notice.cycle")
        elif kind == ALL_SKIPPED:
            text = i18n.t("player.notice.all_skipped")
        else:
            return None
        return {"seq": seq, "text": text}

    def _empty_value(self, empty: object) -> str | None:
        if empty == "no_selection" and not self.playlists.all():
            return "no_playlist"
        return empty if isinstance(empty, str) else None

    # ---------- 钩子 ----------

    def _available(self, md5: str) -> bool:
        if md5 in self._failed:
            return False
        music = self.library.find_music(md5)
        if music is None:
            return False
        return paths.music_path(md5, music.ext).exists()

    def _should_skip(self, playlist_uid: str, md5: str) -> bool:
        playlist = self.playlists.get(playlist_uid)
        if playlist is None or not playlist.adaptation.enabled or self.settings.debug_enabled():
            return False
        if playlist_uid != self._records_uid:
            self._reload_records()
        entry = self._records.get(md5)
        return adaptation.should_skip(
            entry.records if entry else "", self._params(playlist), self._rng
        )

    def _on_auto_skip(self, playlist_uid: str, md5: str) -> None:
        try:
            self.stats.mark_auto_skipped(playlist_uid, md5)
        except Exception:  # 统计写不进去也要继续播
            logger.exception("记录自动跳过失败：{}", md5)
            return
        entry = self._records.setdefault(md5, SongStats())
        entry.auto_skipped += 1
        entry.last_played_at = int(time.time())

    # ---------- 统计 ----------

    def _record_skip(self, md5: object, played_ms: object) -> None:
        """只有「下一首」会走到这里；上一首、点队列、切歌单都不记账。"""
        if isinstance(md5, str) and md5 and md5 == self.session.current_md5:
            self._record(md5, _milliseconds(played_ms), natural=False)

    def _record(self, md5: str, played_ms: int, *, natural: bool) -> None:
        uid = self.session.playlist_uid
        playlist = self.playlists.get(uid) if uid else None
        if playlist is None or not playlist.adaptation.enabled or self.settings.debug_enabled():
            return
        if uid != self._records_uid:
            self._reload_records()
        params = self._params(playlist)
        skipped = False if natural else played_ms < params.skip_seconds * 1000
        try:
            self.stats.record(uid, md5, skipped, params.window)
        except Exception:  # 统计是附加物，不能拦住播放
            logger.exception("统计写入失败：{}", md5)
            return
        entry = self._records.setdefault(md5, SongStats())
        entry.records = adaptation.push(entry.records, skipped, params.window)
        entry.last_played_at = int(time.time())

    def _reload_records(self) -> None:
        uid = self.session.playlist_uid
        if not uid:
            self._records = {}
            self._records_uid = ""
            return
        if uid == self._records_uid:
            return
        try:
            self._records = self.stats.load(uid)
        except AppError:
            self._records = {}
        self._records_uid = uid

    def _params(self, playlist: Playlist) -> adaptation.Params:
        defaults = adaptation.params_from_dict(
            self.settings.get("common", "adaptation", default={})
        )
        return adaptation.effective(playlist.adaptation, defaults)

    # ---------- 持久化 ----------

    def _after_change(self) -> None:
        self._reload_records()
        self._save_progress()
        self._last_save = time.monotonic()

    def _save_progress(self) -> None:
        remember = bool(self.settings.get("player", "remember_progress", default=True))
        position = self.session.position_ms if remember else 0
        try:
            self.settings.patch_player(
                {
                    "last_playlist": self.session.playlist_uid,
                    "last_md5": self.session.current_md5,
                    "last_position_ms": int(position),
                }
            )
        except Exception:
            logger.exception("保存播放位置失败")

    def _save_state(self, window=None) -> None:
        if window is not None:
            try:
                width = int(window.width)
                height = int(window.height)
            except Exception:
                width = height = 0
            if width > 0 and height > 0:
                self._window_size = (
                    max(MIN_SIZE[0], width),
                    max(MIN_SIZE[1], height),
                )
        payload = {
            "version": STATE_VERSION,
            "window": {"width": self._window_size[0], "height": self._window_size[1]},
            "queue_visible": self._queue_visible,
        }
        try:
            atomic.write_json(self.state_path, payload)
        except OSError:
            logger.exception("保存窗口状态失败")

    def _restore(self) -> None:
        uid = self.settings.get("player", "last_playlist", default=None)
        md5 = self.settings.get("player", "last_md5", default=None)
        position = self.settings.get("player", "last_position_ms", default=0)
        remember = bool(self.settings.get("player", "remember_progress", default=True))
        self.session.restore(
            uid if isinstance(uid, str) else None,
            md5 if isinstance(md5, str) else None,
            _milliseconds(position) if remember else 0,
        )

    # ---------- 小工具 ----------

    def _playlist_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for playlist in self.playlists.all():
            try:
                counts[playlist.uid] = len(self.playlists.resolve(playlist.uid, self.library).md5s)
            except AppError:
                counts[playlist.uid] = 0
        return counts

    def _playlist_title(self, playlist: Playlist) -> str:
        return playlist.name or i18n.t("overview.default_playlist")

    def _title(self, md5: str) -> str:
        music = self.library.find_music(md5)
        return music.title if music else md5[:8]

    def _authors_text(self, music: Music) -> str:
        names = self.library.music_authors(music)
        return i18n.t("list.separator").join(names) if names else ""

    def _matches(self, music: Music, authors: str, text: str) -> bool:
        if any(text in name.casefold() for name in music.names):
            return True
        return text in authors.casefold()

    def _media_url(self, md5: str, ext: str) -> str:
        try:
            if self._media is None:
                self._media = MediaServer(paths.MUSIC_DIR)
            return self._media.url(f"{md5}.{ext}")
        except OSError:
            logger.exception("媒体服务不可用")
            return ""
