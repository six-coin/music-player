"""管理器的番茄钟接口。

单独一个 mixin：``api.py`` 已经很长，番茄钟的 CRUD、导入任务与资源 URL 放在
这里，``ManagerApi`` 继承它即可。所有方法都假定宿主已经准备好 ``pomodoro``、
``playlists``、``_lock``、``_window``、``_tasks`` 与 ``_pomo_media``。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import webview
from loguru import logger

from app import i18n, paths
from app.core import pomodoro_media
from app.core.pomodoro import (
    ASSET_KINDS,
    BACKGROUND_MODES,
    FONTS,
    HUD_SCALE_DEFAULT,
    HUD_SCALE_MAX,
    HUD_SCALE_MIN,
    PLAY_ORDERS,
    PomodoroStore,
)
from app.errors import ActionError, DataError
from app.ui.media import MediaHub

POMODORO_KINDS = ("pomodoro", "duration_mode", "background", "ring", "environment")
#: 番茄分区里可以被「选中」的全部类型，含总览。
POMODORO_SELECTION_KINDS = ("pomodoro_overview",) + POMODORO_KINDS


def is_pomodoro_selection(kind: object) -> bool:
    return kind in POMODORO_SELECTION_KINDS


ASSET_FILTERS = {
    "background": (
        "图片或视频 (*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif;*.mp4;*.mov;*.mkv;*.webm;*.avi)",
    ),
    "ring": ("提示音 (*.mp3;*.ogg)",),
    "environment": ("环境音 (*.mp3;*.ogg;*.mp4;*.m4a)",),
}


def _stats(stats) -> dict[str, int]:
    return {
        "focus_ms": stats.focus_ms,
        "rest_ms": stats.rest_ms,
        "total_ms": stats.total_ms,
        "sessions": stats.sessions,
        "last_used_at": stats.last_used_at,
    }


class PomodoroApiMixin:
    # ---------- 快照 ----------

    def _pomodoro_payload(self) -> dict[str, Any]:
        self.pomodoro.reload_if_changed()
        items = [self._pomodoro_item_payload(item) for item in self.pomodoro.item_list()]
        modes = [self._pomodoro_mode_payload(mode) for mode in self.pomodoro.mode_list()]
        backgrounds = [
            self._pomodoro_background_payload(record) for record in self.pomodoro.background_list()
        ]
        rings = [self._pomodoro_audio_payload(record) for record in self.pomodoro.ring_list()]
        environments = [
            self._pomodoro_audio_payload(record) for record in self.pomodoro.environment_list()
        ]
        recent_used = sorted(
            items,
            key=lambda item: item["stats"]["last_used_at"],
            reverse=True,
        )[:5]
        recent_edited = sorted(items, key=lambda item: item["updated_at"], reverse=True)[:5]
        return {
            "items": items,
            "duration_modes": modes,
            "backgrounds": backgrounds,
            "rings": rings,
            "environments": environments,
            "overview": {
                "total": _stats(self.pomodoro.total),
                "counts": {
                    "items": len(items),
                    "duration_modes": len(modes),
                    "backgrounds": len(backgrounds),
                    "rings": len(rings),
                    "environments": len(environments),
                },
                "recent_used": [
                    {
                        "uid": item["uid"],
                        "name": item["name"],
                        "summary": item["summary"],
                        "stats": item["stats"],
                    }
                    for item in recent_used
                    if item["stats"]["last_used_at"] > 0
                ],
                "recent_edited": [
                    {
                        "uid": item["uid"],
                        "name": item["name"],
                        "summary": item["summary"],
                        "updated_at": item["updated_at"],
                    }
                    for item in recent_edited
                ],
            },
            "options": {
                "background_modes": list(BACKGROUND_MODES),
                "fonts": list(FONTS),
                "orders": list(PLAY_ORDERS),
                "playlists": [
                    {"uid": playlist.uid, "title": self._playlist_title(playlist.uid)}
                    for playlist in self.playlists.all()
                ],
            },
            "preferences": {
                "music_volume": self.pomodoro.music_volume,
                "environment_volume": self.pomodoro.environment_volume,
                "hud_scale": self.pomodoro.hud_scale,
                "hud_scale_min": HUD_SCALE_MIN,
                "hud_scale_max": HUD_SCALE_MAX,
            },
        }

    def set_pomodoro_hud_scale(self, value: object = 1.0) -> dict[str, Any]:
        """计时器比例是全局偏好，manager 与 player 改的是同一个值。"""
        with self._lock:
            try:
                self.pomodoro.set_hud_scale(
                    float(value) if isinstance(value, (int, float)) else HUD_SCALE_DEFAULT
                )
            except Exception:
                logger.exception("保存番茄钟计时器比例失败")
                return self._pomodoro_error(i18n.t("pomodoro.invalid"))
            return self._snapshot()

    def _pomodoro_item_payload(self, item) -> dict[str, Any]:
        mode = self.pomodoro.find_mode(item.duration_mode)
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
            "focus": item.focus.to_dict(),
            "rest": item.rest.to_dict(),
            "ring": item.ring,
            "environment": item.environment,
            "font": item.font,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "stats": _stats(self.pomodoro.stats_for(item.uid)),
        }

    def _pomodoro_mode_payload(self, mode) -> dict[str, Any]:
        count = sum(1 for item in self.pomodoro.items.values() if item.duration_mode == mode.uid)
        return {
            "uid": mode.uid,
            "name": mode.name,
            "segments": list(mode.segments),
            "summary": mode.summary,
            "total_minutes": mode.total_minutes,
            "count": count,
            "created_at": mode.created_at,
            "updated_at": mode.updated_at,
        }

    def _pomodoro_background_payload(self, record) -> dict[str, Any]:
        path = paths.data_path(record.file)
        return {
            **record.to_dict(),
            "url": self._pomodoro_asset_url(path),
            "exists": path.is_file(),
        }

    def _pomodoro_audio_payload(self, record) -> dict[str, Any]:
        path = paths.data_path(record.file)
        return {
            **record.to_dict(),
            "url": self._pomodoro_asset_url(path),
            "exists": path.is_file(),
        }

    def _pomodoro_asset_url(self, path: Path) -> str:
        try:
            return self._pomo_media.url(path.parent, path.name)
        except OSError:
            logger.exception("番茄钟媒体服务不可用：{}", path)
            return ""

    # ---------- 选择 ----------

    def select_pomodoro_overview(self) -> dict[str, Any]:
        with self._lock:
            self.section = "pomodoro"
            self.selection = {"kind": "pomodoro_overview", "uid": ""}
            return self._snapshot()

    # ---------- 番茄钟 ----------

    def create_pomodoro(self, name: str) -> dict[str, Any]:
        with self._lock:
            try:
                item = self.pomodoro.create_item(str(name or ""))
            except DataError as error:
                return self._pomodoro_error(str(error))
            self.section = "pomodoro"
            self.selection = {"kind": "pomodoro", "uid": item.uid}
            return self._snapshot()

    def update_pomodoro(self, uid: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            try:
                self.pomodoro.update_item(uid, patch if isinstance(patch, dict) else {})
            except DataError as error:
                return self._pomodoro_error(str(error))
            return self._snapshot()

    def rename_pomodoro(self, uid: str, name: str) -> dict[str, Any]:
        with self._lock:
            try:
                self.pomodoro.update_item(uid, {"name": str(name or "")})
            except DataError:
                return {"ok": False}
            return {"ok": True}

    def delete_pomodoro(self, uid: str) -> dict[str, Any]:
        with self._lock:
            self.pomodoro.delete_item(uid)
            if self.selection and self.selection.get("uid") == uid:
                self.selection = {"kind": "pomodoro_overview", "uid": ""}
            return self._snapshot()

    def reorder_pomodoros(self, order: list[str]) -> dict[str, Any]:
        with self._lock:
            self.pomodoro.reorder_items([str(uid) for uid in order or []])
            return self._snapshot()

    # ---------- 时长模式 ----------

    def create_duration_mode(self, name: str, segments: list[int]) -> dict[str, Any]:
        with self._lock:
            try:
                mode = self.pomodoro.create_mode(str(name or ""), list(segments or []))
            except DataError as error:
                return self._pomodoro_error(str(error))
            self.section = "pomodoro"
            self.selection = {"kind": "duration_mode", "uid": mode.uid}
            return self._snapshot()

    def update_duration_mode(self, uid: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            try:
                self.pomodoro.update_mode(uid, patch if isinstance(patch, dict) else {})
            except DataError as error:
                return self._pomodoro_error(str(error))
            return self._snapshot()

    def rename_duration_mode(self, uid: str, name: str) -> dict[str, Any]:
        with self._lock:
            try:
                self.pomodoro.update_mode(uid, {"name": str(name or "")})
            except DataError:
                return {"ok": False}
            return {"ok": True}

    def delete_duration_mode(self, uid: str) -> dict[str, Any]:
        with self._lock:
            if not self.pomodoro.delete_mode(uid):
                snapshot = self._snapshot()
                snapshot["ok"] = False
                snapshot["message"] = i18n.t("pomodoro.mode.last")
                return snapshot
            if self.selection and self.selection.get("uid") == uid:
                self.selection = {"kind": "pomodoro_overview", "uid": ""}
            return self._snapshot()

    def reorder_duration_modes(self, order: list[str]) -> dict[str, Any]:
        with self._lock:
            self.pomodoro.reorder_modes([str(uid) for uid in order or []])
            return self._snapshot()

    # ---------- 资源 ----------

    def rename_background(self, uid: str, name: str) -> dict[str, Any]:
        return self._rename_asset("background", uid, name)

    def rename_ring(self, uid: str, name: str) -> dict[str, Any]:
        return self._rename_asset("ring", uid, name)

    def rename_environment(self, uid: str, name: str) -> dict[str, Any]:
        return self._rename_asset("environment", uid, name)

    def _rename_asset(self, kind: str, uid: str, name: str) -> dict[str, Any]:
        with self._lock:
            try:
                if kind == "background":
                    self.pomodoro.update_background(uid, str(name or ""))
                elif kind == "ring":
                    self.pomodoro.update_ring(uid, str(name or ""))
                else:
                    self.pomodoro.update_environment(uid, str(name or ""))
            except DataError:
                return {"ok": False}
            return {"ok": True}

    def delete_background(self, uid: str) -> dict[str, Any]:
        return self._delete_asset("background", uid)

    def delete_ring(self, uid: str) -> dict[str, Any]:
        return self._delete_asset("ring", uid)

    def delete_environment(self, uid: str) -> dict[str, Any]:
        return self._delete_asset("environment", uid)

    def _delete_asset(self, kind: str, uid: str) -> dict[str, Any]:
        with self._lock:
            if kind == "background":
                record = self.pomodoro.delete_background(uid)
            elif kind == "ring":
                record = self.pomodoro.delete_ring(uid)
            else:
                record = self.pomodoro.delete_environment(uid)
            if record is not None:
                try:
                    paths.data_path(record.file).unlink(missing_ok=True)
                except OSError:
                    logger.exception("删除番茄钟资源文件失败：{}", record.file)
            if self.selection and self.selection.get("uid") == uid:
                self.selection = {"kind": "pomodoro_overview", "uid": ""}
            return self._snapshot()

    def reorder_backgrounds(self, order: list[str]) -> dict[str, Any]:
        with self._lock:
            self.pomodoro.reorder_backgrounds([str(uid) for uid in order or []])
            return self._snapshot()

    def reorder_rings(self, order: list[str]) -> dict[str, Any]:
        with self._lock:
            self.pomodoro.reorder_rings([str(uid) for uid in order or []])
            return self._snapshot()

    def reorder_environments(self, order: list[str]) -> dict[str, Any]:
        with self._lock:
            self.pomodoro.reorder_environments([str(uid) for uid in order or []])
            return self._snapshot()

    # ---------- 导入 ----------

    def browse_pomodoro_asset(self, kind: str) -> dict[str, Any]:
        if kind not in ASSET_FILTERS:
            return {"path": ""}
        if self._window is None:
            return {"path": ""}
        try:
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                directory=self._start_dir(),
                allow_multiple=False,
                file_types=ASSET_FILTERS[kind],
            )
        except Exception as error:
            logger.error("打开番茄钟文件对话框失败：{}", error)
            return {"path": ""}
        if not result:
            return {"path": ""}
        if isinstance(result, str):
            return {"path": result}
        return {"path": str(result[0])}

    def probe_pomodoro_source(self, path: str) -> dict[str, Any]:
        try:
            return {"ok": True, **pomodoro_media.probe_source(Path(str(path)))}
        except (ActionError, OSError) as error:
            return {"ok": False, "message": str(error)}

    def start_pomodoro_import(
        self,
        kind: str,
        path: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if kind not in ASSET_KINDS:
            return {"task_id": ""}
        source = Path(str(path))
        if not source.is_file():
            return {"task_id": ""}
        task_id = self._register_task(
            {
                "state": "running",
                "kind": "pomodoro",
                "asset_kind": kind,
                "done": 0,
                "total": 1,
                "current": source.name,
                "imported": [],
                "errors": [],
                "result": None,
                "options": options if isinstance(options, dict) else {},
            }
        )
        thread = threading.Thread(
            target=self._run_pomodoro_import,
            args=(task_id, kind, source, options),
            name="pomodoro-import",
            daemon=True,
        )
        thread.start()
        return {"task_id": task_id}

    def _run_pomodoro_import(
        self,
        task_id: str,
        kind: str,
        source: Path,
        options: dict[str, Any] | None,
    ) -> None:
        try:
            if kind == "background":
                record = pomodoro_media.import_background(
                    self.pomodoro,
                    source,
                    pomodoro_media.SegmentOptions.from_dict(options),
                )
            elif kind == "ring":
                record = pomodoro_media.import_ring(self.pomodoro, source)
            else:
                record = pomodoro_media.import_environment(
                    self.pomodoro,
                    source,
                    pomodoro_media.SegmentOptions.from_dict(options),
                )
        except Exception as error:  # 单个资源失败要让进度框能退出
            logger.warning("番茄钟资源导入失败：{}（{}）", source, error)
            self._finish_task(task_id, error=f"{source.name}：{error}")
            return
        with self._lock:
            self.section = "pomodoro"
            self.selection = {"kind": kind, "uid": record.uid}
            self._finish_task(
                task_id,
                result={"uid": record.uid, "kind": kind, "name": record.name},
            )

    def _pomodoro_error(self, message: str) -> dict[str, Any]:
        snapshot = self._snapshot()
        snapshot["ok"] = False
        snapshot["message"] = message
        return snapshot


def make_store(base: Path) -> PomodoroStore:
    return PomodoroStore(base / "pomodoro.json")


def make_media_hub() -> MediaHub:
    return MediaHub()
