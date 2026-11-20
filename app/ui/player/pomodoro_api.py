"""播放器的番茄钟接口。

番茄钟的音乐走一条独立的 ``PlayerSession``：普通播放器的队列、模式、进度都
不受影响，退出番茄钟后原来的界面还在原处。计时器在网页里跑，Python 只接收
「已经流逝、且没有暂停」的时长并累加——网页是计时与音频状态的唯一真相。

与 manager 的接口分开成 mixin，``api.py`` 不会因为番茄钟再长一截。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from loguru import logger

from app import paths
from app.core.player_session import Hooks, PlayerSession
from app.core.pomodoro import (
    BACKGROUND_MODES,
    FONTS,
    PLAY_ORDERS,
    PhaseAudio,
    Pomodoro,
    PomodoroStore,
)
from app.core.pomodoro_sessions import SessionLog, SessionRecord
from app.ui.media import MediaHub


def _milliseconds(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


def _seconds(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


class PomodoroApiMixin:
    # ---------- 初始化 ----------

    def _init_pomodoro(self, base: Path) -> None:
        self.pomodoro = PomodoroStore(base / "pomodoro.json")
        self.pomo_sessions = SessionLog(base / "pomodoro-sessions.json")
        self._pomo_media = MediaHub()
        self.warnings.extend(self.pomodoro.load_locked())
        self.warnings.extend(self.pomo_sessions.load())
        if self.pomodoro.sanitize_playlists(set(self.playlists.items)):
            self.pomodoro.save()
        self._pomo_session = self._new_pomo_session()
        self._pomo_selected: str | None = None
        self._pomo_active: str | None = None
        self._pomo_done = False
        self._pomo_plan: dict[str, Any] | None = None
        self._pomo_phase = 0
        self._pomo_playlist_uid: str | None = None
        self._fullscreen = False

    def _new_pomo_session(self) -> PlayerSession:
        return PlayerSession(
            self.library,
            self.playlists,
            mode="shuffle",
            rng=self._rng,
            hooks=Hooks(self._available, self._should_skip, self._on_auto_skip),
        )

    # ---------- 快照 ----------

    def _pomodoro_snapshot(self) -> dict[str, Any]:
        self.pomodoro.reload_if_changed()
        items = [
            {
                "uid": item.uid,
                "name": item.name,
                "summary": self._pomo_summary(item),
                "total_minutes": self._pomo_total_minutes(item),
                "active": item.uid == self._pomo_active,
            }
            for item in self.pomodoro.item_list()
        ]
        selected = self.pomodoro.find_item(self._pomo_selected or "")
        return {
            "items": items,
            "selected": self._pomodoro_detail(selected) if selected else None,
            "active": self._pomo_active,
            "options": {
                "duration_modes": [
                    {
                        "uid": mode.uid,
                        "name": mode.name,
                        "summary": mode.summary,
                        "total_minutes": mode.total_minutes,
                    }
                    for mode in self.pomodoro.mode_list()
                ],
                "backgrounds": [
                    {
                        "uid": record.uid,
                        "name": record.name,
                        "kind": record.kind,
                        "duration_ms": record.duration_ms,
                        "url": self._pomodoro_asset_url(record.file),
                    }
                    for record in self.pomodoro.background_list()
                ],
                "rings": [
                    {
                        "uid": record.uid,
                        "name": record.name,
                        "duration_ms": record.duration_ms,
                        "url": self._pomodoro_asset_url(record.file),
                    }
                    for record in self.pomodoro.ring_list()
                ],
                "environments": [
                    {
                        "uid": record.uid,
                        "name": record.name,
                        "duration_ms": record.duration_ms,
                        "url": self._pomodoro_asset_url(record.file),
                    }
                    for record in self.pomodoro.environment_list()
                ],
                "playlists": [
                    {"uid": playlist.uid, "title": self._playlist_title(playlist)}
                    for playlist in self.playlists.all()
                ],
                "background_modes": list(BACKGROUND_MODES),
                "fonts": list(FONTS),
                "orders": list(PLAY_ORDERS),
            },
            "preferences": {
                "music_volume": self.pomodoro.music_volume,
                "environment_volume": self.pomodoro.environment_volume,
                "hud_scale": self.pomodoro.hud_scale,
            },
        }

    def _pomodoro_detail(self, item: Pomodoro) -> dict[str, Any]:
        mode = self.pomodoro.find_mode(item.duration_mode)
        background = self.pomodoro.find_background(item.background or "")
        ring = self.pomodoro.find_ring(item.ring or "")
        environment = self.pomodoro.find_environment(item.environment or "")
        return {
            "uid": item.uid,
            "name": item.name,
            "description": item.description,
            "duration_mode": item.duration_mode,
            "duration_mode_name": mode.name if mode else "",
            "summary": mode.summary if mode else "",
            "total_minutes": mode.total_minutes if mode else 0,
            "background": item.background,
            "background_mode": item.background_mode,
            "background_url": self._pomodoro_asset_url(background.file) if background else "",
            "background_kind": background.kind if background else "",
            "focus": item.focus.to_dict(),
            "rest": item.rest.to_dict(),
            "ring": item.ring,
            "ring_url": self._pomodoro_asset_url(ring.file) if ring else "",
            "environment": item.environment,
            "environment_url": (self._pomodoro_asset_url(environment.file) if environment else ""),
            "font": item.font,
            "stats": self._pomo_stats(item.uid),
        }

    def _pomo_summary(self, item: Pomodoro) -> str:
        mode = self.pomodoro.find_mode(item.duration_mode)
        return mode.summary if mode else ""

    def _pomo_total_minutes(self, item: Pomodoro) -> int:
        mode = self.pomodoro.find_mode(item.duration_mode)
        return mode.total_minutes if mode else 0

    def _pomo_stats(self, uid: str) -> dict[str, int]:
        stats = self.pomodoro.stats_for(uid)
        return {
            "focus_ms": stats.focus_ms,
            "rest_ms": stats.rest_ms,
            "total_ms": stats.total_ms,
            "sessions": stats.sessions,
            "last_used_at": stats.last_used_at,
        }

    def _pomodoro_asset_url(self, relative: str) -> str:
        path = paths.data_path(relative)
        if not path.is_file():
            return ""
        try:
            return self._pomo_media.url(path.parent, path.name)
        except OSError:
            return ""

    # ---------- 选择 ----------

    def select_pomodoro(self, uid: object) -> dict[str, Any]:
        with self._lock:
            if self._pomo_active is not None:
                return self._snapshot()
            if isinstance(uid, str) and uid in self.pomodoro.items:
                self._pomo_selected = uid
                # 主区域换成番茄详情后，普通播放器连控件都没有了；歌单高亮和
                # 正在放的那首一起收掉，否则空格还能把看不见的音频放起来。
                # 不写 player.json：下次启动仍停在上次听的歌单。
                if self.session.playlist_uid is not None or self.session.current_md5 is not None:
                    self.session.clear()
                    self._reload_records()
            return self._snapshot()

    def clear_pomodoro(self) -> dict[str, Any]:
        with self._lock:
            if self._pomo_active is None:
                self._pomo_selected = None
            return self._snapshot()

    # ---------- 开始与阶段 ----------

    def pomodoro_start(self, uid: object, overrides: object = None) -> dict[str, Any]:
        with self._lock:
            if self._pomo_active is not None:
                return {"ok": False, "message": "busy"}
            if not isinstance(uid, str):
                return {"ok": False, "message": "pomodoro"}
            item = self.pomodoro.find_item(uid)
            if item is None:
                return {"ok": False, "message": "pomodoro"}
            plan = self._resolve_plan(item, overrides if isinstance(overrides, dict) else {})
            if plan is None:
                return {"ok": False, "message": "pomodoro"}
            self._pomo_active = uid
            self._pomo_done = False
            self._pomo_selected = uid
            self._pomo_plan = plan
            self._pomo_phase = 0
            self._pomo_playlist_uid = None
            self._pomo_session = self._new_pomo_session()
            try:
                self.pomodoro.touch_used(uid)
            except Exception:  # 统计是附加物，写不进去也要能开始
                logger.exception("记录番茄钟最近使用时间失败：{}", uid)
            self.session.set_playing(False)
            return {"ok": True, "plan": plan}

    def pomodoro_phase(self, index: object, overrides: object = None) -> dict[str, Any]:
        """切到第 ``index`` 段：返回这一段要不要放、放哪张歌单、第一条命令。"""
        with self._lock:
            if self._pomo_active is None or self._pomo_plan is None:
                return {"ok": False}
            phase_index = index if isinstance(index, int) and not isinstance(index, bool) else 0
            phase_index = max(0, phase_index)
            phase = "focus" if phase_index % 2 == 0 else "rest"
            config = self._phase_config(phase, overrides if isinstance(overrides, dict) else {})
            self._pomo_phase = phase_index
            if not config["playlist"]:
                return {"ok": True, "phase": phase, "play": False}
            playlist_uid = config["playlist"]
            if self._pomo_session.mode != config["order"]:
                self._pomo_session.set_mode(config["order"])
            if playlist_uid == self._pomo_playlist_uid and self._pomo_session.current_md5:
                return {"ok": True, "phase": phase, "play": True, "resume": True}
            if not self._pomo_session.load_playlist(playlist_uid, autoplay=True):
                return {"ok": True, "phase": phase, "play": False, "reason": "missing"}
            self._pomo_playlist_uid = playlist_uid
            return {
                "ok": True,
                "phase": phase,
                "play": True,
                "command": self._command_payload(self._pomo_session.command),
            }

    def _phase_config(self, phase: str, overrides: dict[str, Any]) -> dict[str, Any]:
        plan = self._pomo_plan or {}
        base = plan.get(phase) or {"playlist": None, "order": "shuffle"}
        raw = overrides.get(phase)
        if not isinstance(raw, dict):
            return base
        playlist = base.get("playlist")
        if "playlist" in raw:
            value = raw.get("playlist")
            if value in ("", None):
                playlist = None
            elif isinstance(value, str) and value in self.playlists.items:
                playlist = value
        order = raw.get("order")
        if order not in PLAY_ORDERS:
            order = base.get("order", "shuffle")
        return {"playlist": playlist, "order": order}

    # ---------- 音乐 ----------

    def pomodoro_music_next(self, md5: object = "", played_ms: object = 0) -> dict[str, Any]:
        with self._lock:
            if self._pomo_active is None:
                return {"ok": False}
            if isinstance(md5, str) and md5 and md5 == self._pomo_session.current_md5:
                self._record_pomodoro(md5, _milliseconds(played_ms), natural=False)
                self._pomo_session.next()
            return {"ok": True, "command": self._command_payload(self._pomo_session.command)}

    def pomodoro_music_ended(self, md5: object = "", played_ms: object = 0) -> dict[str, Any]:
        with self._lock:
            if self._pomo_active is None:
                return {"ok": False}
            if isinstance(md5, str) and md5 and md5 == self._pomo_session.current_md5:
                self._record_pomodoro(md5, _milliseconds(played_ms), natural=True)
                self._pomo_session.on_ended()
            return {"ok": True, "command": self._command_payload(self._pomo_session.command)}

    def pomodoro_music_failed(self, md5: object = "", reason: object = "") -> dict[str, Any]:
        with self._lock:
            if self._pomo_active is None:
                return {"ok": False}
            if isinstance(md5, str) and md5 == self._pomo_session.current_md5:
                self._pomo_session.on_failed(md5)
            return {"ok": True, "command": self._command_payload(self._pomo_session.command)}

    def pomodoro_music_playing(self, on: object = False) -> dict[str, Any]:
        with self._lock:
            self._pomo_session.set_playing(bool(on))
            return {"ok": True}

    def _record_pomodoro(self, md5: str, played_ms: int, *, natural: bool) -> None:
        self._record_song(
            self._pomo_session.playlist_uid,
            self._pomo_session.mode,
            md5,
            played_ms,
            natural=natural,
        )

    # ---------- 计时与音量 ----------

    def pomodoro_report(
        self,
        uid: object,
        focus_ms: object = 0,
        rest_ms: object = 0,
        completed: object = False,
    ) -> dict[str, Any]:
        if not isinstance(uid, str):
            return {"ok": False}
        # 完成页已经是「走完了」的状态：这时候关窗不该再拦。
        if completed:
            self._pomo_done = True
        try:
            self.pomodoro.add_time(
                uid,
                focus_ms=_milliseconds(focus_ms),
                rest_ms=_milliseconds(rest_ms),
                completed=bool(completed),
            )
        except Exception:  # 统计写不进去不该把计时器打断
            logger.exception("记录番茄钟时长失败：{}", uid)
            return {"ok": False}
        return {"ok": True}

    def pomodoro_set_volumes(
        self, music: object = 0.5, environment: object = 0.35
    ) -> dict[str, Any]:
        try:
            self.pomodoro.set_preferences(
                {
                    "music_volume": float(music) if isinstance(music, (int, float)) else 0.5,
                    "environment_volume": (
                        float(environment) if isinstance(environment, (int, float)) else 0.35
                    ),
                }
            )
        except Exception:
            logger.exception("保存番茄钟音量失败")
            return {"ok": False}
        return {"ok": True}

    def pomodoro_set_hud_scale(self, value: object = 1.0) -> dict[str, Any]:
        try:
            self.pomodoro.set_preferences(
                {"hud_scale": float(value) if isinstance(value, (int, float)) else 1.0}
            )
        except Exception:
            logger.exception("保存番茄钟计时器比例失败")
            return {"ok": False}
        return {"ok": True}

    def pomodoro_record_session(
        self,
        uid: object,
        started_at: object = 0,
        focus_ms: object = 0,
        rest_ms: object = 0,
    ) -> dict[str, Any]:
        """完整走完一轮时追加一条播放记录。网页给开始时间与两个累计时长。"""
        if not isinstance(uid, str) or not uid:
            return {"ok": False}
        focus = _milliseconds(focus_ms)
        rest = _milliseconds(rest_ms)
        ended_at = int(time.time())
        started = _seconds(started_at) or max(0, ended_at - (focus + rest) // 1000)
        record = SessionRecord(
            uid=uid,
            started_at=started,
            ended_at=ended_at,
            focus_ms=focus,
            rest_ms=rest,
        )
        try:
            self.pomo_sessions.append(record)
        except Exception:  # 记录是附加物，写不进去不该把完成页卡住
            logger.exception("记录番茄钟播放失败：{}", uid)
            return {"ok": False}
        return {"ok": True}

    def pomodoro_finish(self, uid: object = "") -> dict[str, Any]:
        with self._lock:
            self._pomo_active = None
            self._pomo_done = False
            self._pomo_plan = None
            self._pomo_phase = 0
            self._pomo_playlist_uid = None
            self._pomo_session = self._new_pomo_session()
            return self._snapshot()

    def set_fullscreen(self, on: object = False) -> dict[str, Any]:
        want = bool(on)
        window = self._window
        if window is not None and want != self._fullscreen:
            try:
                window.toggle_fullscreen()
                self._fullscreen = want
            except Exception:
                return {"ok": False, "fullscreen": self._fullscreen}
        return {"ok": True, "fullscreen": self._fullscreen}

    # ---------- 计划 ----------

    def _resolve_plan(self, item: Pomodoro, overrides: dict[str, Any]) -> dict[str, Any] | None:
        mode_uid = self._override_uid(
            overrides,
            "duration_mode",
            self.pomodoro.duration_modes,
            item.duration_mode,
        )
        mode = self.pomodoro.find_mode(mode_uid or "")
        if mode is None:
            return None
        background_uid = self._override_uid(
            overrides, "background", self.pomodoro.backgrounds, item.background
        )
        ring_uid = self._override_uid(overrides, "ring", self.pomodoro.rings, item.ring)
        environment_uid = self._override_uid(
            overrides, "environment", self.pomodoro.environments, item.environment
        )
        background_mode = overrides.get("background_mode")
        if background_mode not in BACKGROUND_MODES:
            background_mode = item.background_mode
        font = overrides.get("font")
        if font not in FONTS:
            font = item.font
        focus = self._phase_plan(item.focus, overrides.get("focus"))
        rest = self._phase_plan(item.rest, overrides.get("rest"))
        background = self.pomodoro.find_background(background_uid or "")
        ring = self.pomodoro.find_ring(ring_uid or "")
        environment = self.pomodoro.find_environment(environment_uid or "")
        background_url = self._pomodoro_asset_url(background.file) if background else ""
        ring_url = self._pomodoro_asset_url(ring.file) if ring else ""
        environment_url = self._pomodoro_asset_url(environment.file) if environment else ""
        return {
            "uid": item.uid,
            "name": item.name,
            "mode_name": mode.name,
            "segments": list(mode.segments),
            "background": (
                {"url": background_url, "kind": background.kind}
                if background and background_url
                else None
            ),
            "background_mode": background_mode,
            "ring": {"url": ring_url} if ring and ring_url else None,
            "environment": ({"url": environment_url} if environment and environment_url else None),
            "focus": focus,
            "rest": rest,
            "font": font,
            "music_volume": self.pomodoro.music_volume,
            "environment_volume": self.pomodoro.environment_volume,
            "hud_scale": self.pomodoro.hud_scale,
            "prep_seconds": self.pomodoro.prep_seconds,
            "duck_ms": self.pomodoro.duck_ms,
            "duck_ratio": self.pomodoro.duck_ratio,
            "fade_in_ms": self.pomodoro.fade_in_ms,
        }

    def _override_uid(
        self,
        overrides: dict[str, Any],
        key: str,
        valid: dict,
        fallback: str | None,
    ) -> str | None:
        if key not in overrides:
            return fallback
        value = overrides.get(key)
        if value in ("", None):
            return None
        if isinstance(value, str) and value in valid:
            return value
        return fallback

    def _phase_plan(self, base: PhaseAudio, raw: object) -> dict[str, Any]:
        playlist = base.playlist
        order = base.order
        if isinstance(raw, dict):
            if "playlist" in raw:
                value = raw.get("playlist")
                if value in ("", None):
                    playlist = None
                elif isinstance(value, str) and value in self.playlists.items:
                    playlist = value
            if raw.get("order") in PLAY_ORDERS:
                order = str(raw.get("order"))
        if playlist is not None and playlist not in self.playlists.items:
            playlist = None
        return {"playlist": playlist, "order": order}
