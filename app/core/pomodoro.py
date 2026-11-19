"""番茄钟的读写与全部编辑动作。

一份 ``pomodoro.json`` 装下全部东西：时长模式、背景 / 提示音 / 环境音的登记、
番茄钟定义、累计统计与两个全局音量。资源文件放在 ``pomodoro/`` 下的三个
文件夹里，登记表只写以数据目录为基准的相对路径——数据目录整体搬走时不用改。

写入策略与 ``settings.json`` 一致：读改写全程持有文件锁，落盘走「临时文件 +
原子替换」。manager 与 player 可能同时写这一份文件（前者改配置，后者每 10 秒
记一次时长），所以每次修改都重新读盘、合并、再写，不能用内存里的旧值整份覆盖。

暂停不算时长，这条规则不在这里实现——调用方只把「真正流逝的时间」送进来，
本模块只负责累加。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from loguru import logger

from app import paths
from app.core.pomodoro_models import (
    ASSET_KINDS,
    AUDIO_EXTS,
    BACKGROUND_KINDS,
    BACKGROUND_MODES,
    DUCK_MS_DEFAULT,
    DUCK_MS_MAX,
    DUCK_MS_MIN,
    DUCK_RATIO_DEFAULT,
    DUCK_RATIO_MAX,
    DUCK_RATIO_MIN,
    FADE_IN_MS_DEFAULT,
    FADE_IN_MS_MAX,
    FADE_IN_MS_MIN,
    FONTS,
    HUD_SCALE_DEFAULT,
    HUD_SCALE_MAX,
    HUD_SCALE_MIN,
    MODE_MAX_SEGMENTS,
    MODE_MIN_SEGMENTS,
    PHASES,
    PLAY_ORDERS,
    POMODORO_VERSION,
    PREP_DEFAULT,
    PREP_MAX,
    PREP_MIN,
    SEGMENT_MAX_MINUTES,
    SEGMENT_MIN_MINUTES,
    VOLUME_DEFAULT,
    AudioAsset,
    Background,
    DurationMode,
    PhaseAudio,
    Pomodoro,
    TimeStats,
    _bounded_int,
    _choice,
    _fill_default_modes,
    _in_folder,
    _now,
    _ratio,
    _repair_references,
    _scale,
    _uid_or_none,
)
from app.errors import ConfigError, DataError
from app.models import _integer, _text, new_uid
from app.system import atomic
from app.system.filelock import exclusive

T = TypeVar("T")

__all__ = [
    "ASSET_KINDS",
    "AUDIO_EXTS",
    "BACKGROUND_KINDS",
    "BACKGROUND_MODES",
    "DUCK_MS_DEFAULT",
    "DUCK_MS_MAX",
    "DUCK_RATIO_DEFAULT",
    "DUCK_RATIO_MAX",
    "FADE_IN_MS_DEFAULT",
    "FADE_IN_MS_MAX",
    "FONTS",
    "HUD_SCALE_DEFAULT",
    "HUD_SCALE_MAX",
    "HUD_SCALE_MIN",
    "MODE_MAX_SEGMENTS",
    "MODE_MIN_SEGMENTS",
    "PHASES",
    "PLAY_ORDERS",
    "POMODORO_VERSION",
    "PREP_DEFAULT",
    "PREP_MAX",
    "SEGMENT_MAX_MINUTES",
    "SEGMENT_MIN_MINUTES",
    "VOLUME_DEFAULT",
    "AudioAsset",
    "Background",
    "DurationMode",
    "PhaseAudio",
    "Pomodoro",
    "PomodoroStore",
    "TimeStats",
    "default_store",
]


class PomodoroStore:
    """``pomodoro.json`` 的读写与全部编辑动作。

    对外的方法都走 :meth:`_transact`：锁内重新读盘、改、写。这样 manager 改配置
    与 player 每 10 秒记时长不会互相覆盖。
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.duration_modes: dict[str, DurationMode] = {}
        self.backgrounds: dict[str, Background] = {}
        self.rings: dict[str, AudioAsset] = {}
        self.environments: dict[str, AudioAsset] = {}
        self.items: dict[str, Pomodoro] = {}
        self.total = TimeStats()
        self.item_stats: dict[str, TimeStats] = {}
        self.music_volume = VOLUME_DEFAULT["music"]
        self.environment_volume = VOLUME_DEFAULT["environment"]
        self.hud_scale = HUD_SCALE_DEFAULT
        self.prep_seconds = PREP_DEFAULT
        self.duck_ms = DUCK_MS_DEFAULT
        self.duck_ratio = DUCK_RATIO_DEFAULT
        self.fade_in_ms = FADE_IN_MS_DEFAULT
        self.warnings: list[str] = []
        self._signature: tuple[int, int] | None = None

    # ---------- 读写 ----------

    def load_locked(self) -> list[str]:
        """启动时用：锁内读，文件不存在时只让一个进程创建默认模式。

        manager 与 player 可能同时启动；如果两边都在锁外判断「文件不存在」，
        就会各自生成一套时长模式，后写的覆盖先写的，先启动那一边内存里的
        模式 uid 就与磁盘对不上了。
        """
        with exclusive(paths.lock_for(self.path)):
            return self.load()

    def load(self) -> list[str]:
        # 先全部读到局部变量，最后一次性换到 self 上：另一个线程正在遍历旧字典
        # 时不会看到「清空到一半」的状态。
        warnings: list[str] = []
        self.warnings = warnings
        modes: dict[str, DurationMode] = {}
        backgrounds: dict[str, Background] = {}
        rings: dict[str, AudioAsset] = {}
        environments: dict[str, AudioAsset] = {}
        items: dict[str, Pomodoro] = {}
        item_stats: dict[str, TimeStats] = {}
        total = TimeStats()
        music_volume = VOLUME_DEFAULT["music"]
        environment_volume = VOLUME_DEFAULT["environment"]
        hud_scale = HUD_SCALE_DEFAULT
        prep_seconds = PREP_DEFAULT
        duck_ms = DUCK_MS_DEFAULT
        duck_ratio = DUCK_RATIO_DEFAULT
        fade_in_ms = FADE_IN_MS_DEFAULT
        changed = False

        def commit() -> list[str]:
            self.duration_modes = modes
            self.backgrounds = backgrounds
            self.rings = rings
            self.environments = environments
            self.items = items
            self.item_stats = item_stats
            self.total = total
            self.music_volume = music_volume
            self.environment_volume = environment_volume
            self.hud_scale = hud_scale
            self.prep_seconds = prep_seconds
            self.duck_ms = duck_ms
            self.duck_ratio = duck_ratio
            self.fade_in_ms = fade_in_ms
            return list(warnings)

        if not self.path.exists():
            changed = _fill_default_modes(modes)
            commit()
            self.save()
            return list(warnings)

        try:
            raw = atomic.read_json(self.path)
        except ConfigError as error:
            self._backup_broken(error)
            _fill_default_modes(modes)
            commit()
            self.save()
            return list(warnings)
        if not isinstance(raw, dict):
            self._backup_broken(ConfigError("番茄钟数据顶层必须是对象"))
            _fill_default_modes(modes)
            commit()
            self.save()
            return list(warnings)

        for item in self._records(raw, "duration_modes", "时长模式"):
            self._load_record(item, DurationMode, modes, "时长模式")
        for item in self._records(raw, "backgrounds", "背景"):
            self._load_record(item, Background, backgrounds, "背景")
        for item in self._records(raw, "rings", "提示音"):
            self._load_record(item, AudioAsset, rings, "提示音", "pomodoro/ring")
        for item in self._records(raw, "environments", "环境音"):
            self._load_record(item, AudioAsset, environments, "环境音", "pomodoro/environment")
        for item in self._records(raw, "items", "番茄钟"):
            self._load_record(item, Pomodoro, items, "番茄钟")

        changed = _fill_default_modes(modes) or changed
        changed = _repair_references(modes, backgrounds, rings, environments, items) or changed

        stats = raw.get("stats")
        if isinstance(stats, dict):
            total = TimeStats.from_dict(stats.get("total"))
            raw_items = stats.get("items")
            if isinstance(raw_items, dict):
                for uid, value in raw_items.items():
                    if isinstance(uid, str) and uid in items:
                        item_stats[uid] = TimeStats.from_dict(value)
        preferences = raw.get("preferences")
        if isinstance(preferences, dict):
            music_volume = _ratio(preferences.get("music_volume"), VOLUME_DEFAULT["music"])
            environment_volume = _ratio(
                preferences.get("environment_volume"), VOLUME_DEFAULT["environment"]
            )
            hud_scale = _scale(preferences.get("hud_scale"), HUD_SCALE_DEFAULT)
            prep_seconds = _bounded_int(
                preferences.get("prep_seconds"), PREP_MIN, PREP_MAX, PREP_DEFAULT
            )
            duck_ms = _bounded_int(
                preferences.get("duck_ms"), DUCK_MS_MIN, DUCK_MS_MAX, DUCK_MS_DEFAULT
            )
            duck_ratio = min(
                DUCK_RATIO_MAX,
                max(DUCK_RATIO_MIN, _ratio(preferences.get("duck_ratio"), DUCK_RATIO_DEFAULT)),
            )
            fade_in_ms = _bounded_int(
                preferences.get("fade_in_ms"), FADE_IN_MS_MIN, FADE_IN_MS_MAX, FADE_IN_MS_DEFAULT
            )

        commit()
        if changed:
            # 补出来的默认模式、退回默认模式的引用都要立刻落盘：否则下次启动
            # 会生成新的模式 uid，番茄钟的引用就永远对不上了。
            self.save()
        self._signature = self._stat_signature()
        return list(warnings)

    def _records(self, raw: dict[str, Any], key: str, label: str) -> list[Any]:
        value = raw.get(key) or []
        if not isinstance(value, list):
            self.warnings.append(f"{label}列表格式错误，整段已跳过")
            return []
        return value

    def _load_record(
        self,
        raw: Any,
        model,
        target: dict,
        label: str,
        folder: str = "",
    ) -> None:
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
        if folder and not _in_folder(record.file, folder):
            self.warnings.append(f"{label}记录已跳过：文件必须放在 {folder} 下")
            return
        if record.uid in target:
            self.warnings.append(f"{label}记录重复，已跳过：{record.uid}")
            return
        target[record.uid] = record

    def _backup_broken(self, error: Exception) -> None:
        backup = Path(f"{self.path}.bad")
        if backup.exists():
            backup = Path(f"{self.path}.bad-{_now()}")
        try:
            self.path.replace(backup)
        except OSError:
            logger.exception("备份损坏的番茄钟数据失败")
        self.warnings.append(f"番茄钟数据已损坏（{error}），已备份为 {backup.name}，本次从空白开始")
        logger.warning("番茄钟数据已损坏：{}", error)

    def save(self) -> None:
        atomic.write_json(self.path, self.to_payload())
        self._signature = self._stat_signature()

    def _stat_signature(self) -> tuple[int, int] | None:
        try:
            stat = self.path.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def reload_if_changed(self) -> None:
        """另一个进程改过文件时重新读一遍；没变就什么都不做。"""
        if self._stat_signature() != self._signature:
            self.load()

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": POMODORO_VERSION,
            "duration_modes": [item.to_dict() for item in self.duration_modes.values()],
            "backgrounds": [item.to_dict() for item in self.backgrounds.values()],
            "rings": [item.to_dict() for item in self.rings.values()],
            "environments": [item.to_dict() for item in self.environments.values()],
            "items": [item.to_dict() for item in self.items.values()],
            "stats": {
                "total": self.total.to_dict(),
                "items": {uid: stats.to_dict() for uid, stats in self.item_stats.items()},
            },
            "preferences": {
                "music_volume": self.music_volume,
                "environment_volume": self.environment_volume,
                "hud_scale": self.hud_scale,
                "prep_seconds": self.prep_seconds,
                "duck_ms": self.duck_ms,
                "duck_ratio": self.duck_ratio,
                "fade_in_ms": self.fade_in_ms,
            },
        }

    def _adopt(self, other: PomodoroStore) -> None:
        self.duration_modes = other.duration_modes
        self.backgrounds = other.backgrounds
        self.rings = other.rings
        self.environments = other.environments
        self.items = other.items
        self.total = other.total
        self.item_stats = other.item_stats
        self.music_volume = other.music_volume
        self.environment_volume = other.environment_volume
        self.hud_scale = other.hud_scale
        self.prep_seconds = other.prep_seconds
        self.duck_ms = other.duck_ms
        self.duck_ratio = other.duck_ratio
        self.fade_in_ms = other.fade_in_ms
        self.warnings = other.warnings
        self._signature = other._signature

    def _transact(self, action: Callable[[PomodoroStore], T]) -> T:
        with exclusive(paths.lock_for(self.path)):
            fresh = PomodoroStore(self.path)
            fresh.load()
            result = action(fresh)
            fresh.save()
            self._adopt(fresh)
            return result

    # ---------- 查询 ----------

    def mode_list(self) -> list[DurationMode]:
        return list(self.duration_modes.values())

    def background_list(self) -> list[Background]:
        return list(self.backgrounds.values())

    def ring_list(self) -> list[AudioAsset]:
        return list(self.rings.values())

    def environment_list(self) -> list[AudioAsset]:
        return list(self.environments.values())

    def item_list(self) -> list[Pomodoro]:
        return list(self.items.values())

    def find_mode(self, uid: str) -> DurationMode | None:
        return self.duration_modes.get(uid)

    def find_background(self, uid: str) -> Background | None:
        return self.backgrounds.get(uid)

    def find_ring(self, uid: str) -> AudioAsset | None:
        return self.rings.get(uid)

    def find_environment(self, uid: str) -> AudioAsset | None:
        return self.environments.get(uid)

    def find_item(self, uid: str) -> Pomodoro | None:
        return self.items.get(uid)

    def stats_for(self, uid: str) -> TimeStats:
        return self.item_stats.get(uid, TimeStats())

    def referrers(self, kind: str, uid: str) -> list[Pomodoro]:
        if kind == "duration_mode":
            return [item for item in self.items.values() if item.duration_mode == uid]
        if kind == "background":
            return [item for item in self.items.values() if item.background == uid]
        if kind == "ring":
            return [item for item in self.items.values() if item.ring == uid]
        if kind == "environment":
            return [item for item in self.items.values() if item.environment == uid]
        return []

    # ---------- 时长模式 ----------

    def create_mode(self, name: str, segments: list[int]) -> DurationMode:
        return self._transact(lambda store: store._create_mode(name, segments))

    def _create_mode(self, name: str, segments: list[int]) -> DurationMode:
        now = _now()
        mode = DurationMode(uid=new_uid(), name=name, segments=list(segments))
        mode.normalize()
        mode.validate()
        mode.created_at = now
        mode.updated_at = now
        self.duration_modes[mode.uid] = mode
        return mode

    def update_mode(self, uid: str, patch: dict[str, Any]) -> DurationMode:
        return self._transact(lambda store: store._update_mode(uid, patch))

    def _update_mode(self, uid: str, patch: dict[str, Any]) -> DurationMode:
        mode = self.duration_modes.get(uid)
        if mode is None:
            raise DataError("时长模式不存在")
        if "name" in patch:
            mode.name = _text(patch.get("name"), "时长模式名称")
        if "description" in patch:
            mode.description = _text(patch.get("description"), "时长模式描述")
        if "segments" in patch:
            raw = patch.get("segments")
            if not isinstance(raw, list):
                raise DataError("时长模式的 segments 必须是列表")
            mode.segments = [_integer(value, "单段时长") for value in raw]
        mode.normalize()
        mode.validate()
        mode.updated_at = _now()
        return mode

    def delete_mode(self, uid: str) -> bool:
        return self._transact(lambda store: store._delete_mode(uid))

    def _delete_mode(self, uid: str) -> bool:
        if uid not in self.duration_modes:
            return False
        if len(self.duration_modes) <= 1:
            return False
        order = [mode.uid for mode in self.duration_modes.values() if mode.uid != uid]
        fallback = order[0]
        for item in self.items.values():
            if item.duration_mode == uid:
                item.duration_mode = fallback
                item.updated_at = _now()
        del self.duration_modes[uid]
        return True

    def reorder_modes(self, order: list[str]) -> None:
        self._transact(lambda store: store._reorder(store.duration_modes, order))

    # ---------- 番茄钟 ----------

    def create_item(self, name: str) -> Pomodoro:
        return self._transact(lambda store: store._create_item(name))

    def _create_item(self, name: str) -> Pomodoro:
        mode = next(iter(self.duration_modes.values()), None)
        if mode is None:
            raise DataError("还没有可用的时长模式")
        now = _now()
        item = Pomodoro(
            uid=new_uid(),
            name=name,
            duration_mode=mode.uid,
            focus=PhaseAudio(order="shuffle"),
            rest=PhaseAudio(order="shuffle"),
            created_at=now,
            updated_at=now,
        )
        item.normalize()
        item.validate()
        self.items[item.uid] = item
        return item

    def update_item(self, uid: str, patch: dict[str, Any]) -> Pomodoro:
        return self._transact(lambda store: store._update_item(uid, patch))

    def _update_item(self, uid: str, patch: dict[str, Any]) -> Pomodoro:
        item = self.items.get(uid)
        if item is None:
            raise DataError("番茄钟不存在")
        if "name" in patch:
            item.name = _text(patch.get("name"), "番茄钟名称")
        if "description" in patch:
            item.description = _text(patch.get("description"), "番茄钟描述")
        if "duration_mode" in patch:
            mode = _text(patch.get("duration_mode"), "时长模式")
            if mode not in self.duration_modes:
                raise DataError("时长模式不存在")
            item.duration_mode = mode
        if "background" in patch:
            value = _uid_or_none(patch.get("background"), "背景标识")
            if value is not None and value not in self.backgrounds:
                raise DataError("背景不存在")
            item.background = value
        if "background_mode" in patch:
            item.background_mode = _choice(
                patch.get("background_mode"), BACKGROUND_MODES, "背景铺放方式", "cover"
            )
        if "focus" in patch:
            item.focus = self._phase_patch(item.focus, patch.get("focus"))
        if "rest" in patch:
            item.rest = self._phase_patch(item.rest, patch.get("rest"))
        if "ring" in patch:
            value = _uid_or_none(patch.get("ring"), "提示音标识")
            if value is not None and value not in self.rings:
                raise DataError("提示音不存在")
            item.ring = value
        if "environment" in patch:
            value = _uid_or_none(patch.get("environment"), "环境音标识")
            if value is not None and value not in self.environments:
                raise DataError("环境音不存在")
            item.environment = value
        if "font" in patch:
            item.font = _choice(patch.get("font"), FONTS, "字体", "system")
        item.normalize()
        item.validate()
        item.updated_at = _now()
        return item

    def _phase_patch(self, current: PhaseAudio, raw: object) -> PhaseAudio:
        if not isinstance(raw, dict):
            return current
        playlist = current.playlist
        order = current.order
        if "playlist" in raw:
            playlist = _uid_or_none(raw.get("playlist"), "歌单标识")
        if "order" in raw:
            order = _choice(raw.get("order"), PLAY_ORDERS, "播放顺序", "shuffle")
        return PhaseAudio(playlist=playlist, order=order)

    def delete_item(self, uid: str) -> bool:
        return self._transact(lambda store: store._delete_item(uid))

    def _delete_item(self, uid: str) -> bool:
        if uid not in self.items:
            return False
        del self.items[uid]
        self.item_stats.pop(uid, None)
        return True

    def reorder_items(self, order: list[str]) -> None:
        self._transact(lambda store: store._reorder(store.items, order))

    def drop_playlist(self, uid: str) -> int:
        return self._transact(lambda store: store._drop_playlist(uid))

    def _drop_playlist(self, uid: str) -> int:
        changed = 0
        for item in self.items.values():
            touched = False
            for phase in (item.focus, item.rest):
                if phase.playlist == uid:
                    phase.playlist = None
                    touched = True
            if touched:
                item.updated_at = _now()
                changed += 1
        return changed

    def sanitize_playlists(self, known: set[str]) -> int:
        """清掉指向已删除歌单的引用，返回改动的番茄钟数。

        不在这里写盘：启动阶段调用方拿到结果后再决定是否保存，避免读设置时
        顺手写文件。
        """
        changed = 0
        for item in self.items.values():
            touched = False
            for phase in (item.focus, item.rest):
                if phase.playlist is not None and phase.playlist not in known:
                    phase.playlist = None
                    touched = True
            if touched:
                changed += 1
        return changed

    # ---------- 背景 / 提示音 / 环境音 ----------

    def add_background(self, record: Background) -> Background:
        return self._transact(lambda store: store._add_background(record))

    def _add_background(self, record: Background) -> Background:
        record.normalize()
        record.validate()
        self.backgrounds[record.uid] = record
        return record

    def update_background(self, uid: str, patch: dict[str, Any]) -> Background:
        return self._transact(lambda store: store._update_asset(store.backgrounds, uid, patch))

    def delete_background(self, uid: str) -> Background | None:
        return self._transact(lambda store: store._delete_asset("background", uid))

    def reorder_backgrounds(self, order: list[str]) -> None:
        self._transact(lambda store: store._reorder(store.backgrounds, order))

    def add_ring(self, record: AudioAsset) -> AudioAsset:
        return self._transact(lambda store: store._add_audio(store.rings, record, "pomodoro/ring"))

    def update_ring(self, uid: str, patch: dict[str, Any]) -> AudioAsset:
        return self._transact(lambda store: store._update_asset(store.rings, uid, patch))

    def delete_ring(self, uid: str) -> AudioAsset | None:
        return self._transact(lambda store: store._delete_asset("ring", uid))

    def reorder_rings(self, order: list[str]) -> None:
        self._transact(lambda store: store._reorder(store.rings, order))

    def add_environment(self, record: AudioAsset) -> AudioAsset:
        return self._transact(
            lambda store: store._add_audio(store.environments, record, "pomodoro/environment")
        )

    def update_environment(self, uid: str, patch: dict[str, Any]) -> AudioAsset:
        return self._transact(lambda store: store._update_asset(store.environments, uid, patch))

    def delete_environment(self, uid: str) -> AudioAsset | None:
        return self._transact(lambda store: store._delete_asset("environment", uid))

    def reorder_environments(self, order: list[str]) -> None:
        self._transact(lambda store: store._reorder(store.environments, order))

    def _add_audio(
        self,
        target: dict[str, AudioAsset],
        record: AudioAsset,
        folder: str,
    ) -> AudioAsset:
        record.normalize()
        record.validate()
        if not _in_folder(record.file, folder):
            raise DataError(f"音频文件必须放在 {folder} 下")
        target[record.uid] = record
        return record

    def _update_asset(self, target: dict, uid: str, patch: dict[str, Any]) -> Any:
        record = target.get(uid)
        if record is None:
            raise DataError("资源不存在")
        if "name" in patch:
            record.name = _text(patch.get("name"), "名称")
            if not record.name:
                raise DataError("名称不能为空")
        if "description" in patch:
            record.description = _text(patch.get("description"), "描述")
        record.updated_at = _now()
        return record

    def _delete_asset(self, kind: str, uid: str) -> Any:
        target = {
            "background": self.backgrounds,
            "ring": self.rings,
            "environment": self.environments,
        }[kind]
        record = target.pop(uid, None)
        if record is None:
            return None
        for item in self.items.values():
            if kind == "background" and item.background == uid:
                item.background = None
                item.updated_at = _now()
            elif kind == "ring" and item.ring == uid:
                item.ring = None
                item.updated_at = _now()
            elif kind == "environment" and item.environment == uid:
                item.environment = None
                item.updated_at = _now()
        return record

    def _reorder(self, target: dict, order: list[str]) -> None:
        result: dict[str, Any] = {}
        for uid in order:
            if uid in target:
                result[uid] = target[uid]
        for uid, value in target.items():
            if uid not in result:
                result[uid] = value
        target.clear()
        target.update(result)

    # ---------- 统计 ----------

    def touch_used(self, uid: str) -> None:
        self._transact(lambda store: store._touch_used(uid))

    def _touch_used(self, uid: str) -> None:
        if uid not in self.items:
            return
        stats = self.item_stats.setdefault(uid, TimeStats())
        stats.last_used_at = _now()

    def add_time(
        self,
        uid: str,
        *,
        focus_ms: int = 0,
        rest_ms: int = 0,
        completed: bool = False,
    ) -> None:
        self._transact(lambda store: store._add_time(uid, focus_ms, rest_ms, completed))

    def _add_time(self, uid: str, focus_ms: int, rest_ms: int, completed: bool) -> None:
        focus = max(0, int(focus_ms))
        rest = max(0, int(rest_ms))
        self.total.focus_ms += focus
        self.total.rest_ms += rest
        if completed:
            self.total.sessions += 1
        if uid not in self.items:
            # 番茄钟已被删掉：总时长照记，单项统计不再保留（用户明确要求）。
            return
        stats = self.item_stats.setdefault(uid, TimeStats())
        stats.focus_ms += focus
        stats.rest_ms += rest
        if completed:
            stats.sessions += 1
        stats.last_used_at = max(stats.last_used_at, _now())

    def set_volumes(self, music: float, environment: float) -> None:
        self.set_preferences({"music_volume": music, "environment_volume": environment})

    def set_hud_scale(self, value: float) -> None:
        self.set_preferences({"hud_scale": value})

    def set_preferences(self, patch: dict[str, Any]) -> None:
        """改全局偏好。只处理认识的键，值一律夹取，非法值回退默认。"""
        self._transact(lambda store: store._set_preferences(patch))

    def _set_preferences(self, patch: dict[str, Any]) -> None:
        if "music_volume" in patch:
            self.music_volume = _ratio(patch.get("music_volume"), VOLUME_DEFAULT["music"])
        if "environment_volume" in patch:
            self.environment_volume = _ratio(
                patch.get("environment_volume"), VOLUME_DEFAULT["environment"]
            )
        if "hud_scale" in patch:
            self.hud_scale = _scale(patch.get("hud_scale"), HUD_SCALE_DEFAULT)
        if "prep_seconds" in patch:
            self.prep_seconds = _bounded_int(
                patch.get("prep_seconds"), PREP_MIN, PREP_MAX, PREP_DEFAULT
            )
        if "duck_ms" in patch:
            self.duck_ms = _bounded_int(
                patch.get("duck_ms"), DUCK_MS_MIN, DUCK_MS_MAX, DUCK_MS_DEFAULT
            )
        if "duck_ratio" in patch:
            self.duck_ratio = min(
                DUCK_RATIO_MAX,
                max(DUCK_RATIO_MIN, _ratio(patch.get("duck_ratio"), DUCK_RATIO_DEFAULT)),
            )
        if "fade_in_ms" in patch:
            self.fade_in_ms = _bounded_int(
                patch.get("fade_in_ms"), FADE_IN_MS_MIN, FADE_IN_MS_MAX, FADE_IN_MS_DEFAULT
            )


def default_store() -> PomodoroStore:
    return PomodoroStore(paths.POMODORO_PATH)
