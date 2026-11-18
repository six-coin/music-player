"""设置读写。

读的时候夹取、不信任文件；未知键原样保留，保存时不会丢用户手写的扩展字段。
内存里保持与磁盘一致的嵌套结构，层级只有两层，没必要再拍平。
"""

from __future__ import annotations

import copy
import time
from pathlib import Path
from typing import Any

from app import i18n, keymap, logging_setup, paths
from app.errors import ConfigError
from app.models import Adaptation
from app.system import atomic
from app.system import theme as theme_tool
from app.system.filelock import exclusive

THEMES = ("light", "dark")
SIMPLE_ORDERS = ("shuffle", "list_loop")
PLAYER_ORDERS = ("shuffle", "list_loop", "repeat_one")

DEBUG_CACHE_SECONDS = 2.0

DEFAULTS: dict[str, Any] = {
    "version": 1,
    "common": {
        "theme": "light",
        "language": "zh-CN",
        "debug": False,
        "record_total_plays": True,
        # 日志三件套：三个程序共用一份，改一处三处都变。
        "log_level": logging_setup.DEFAULT_LEVEL,
        "log_cleanup": True,
        "log_retention_days": logging_setup.DEFAULT_RETENTION_DAYS,
        "adaptation": {
            "window": 100,
            "min_plays": 10,
            "base": 0.95,
            "skip_seconds": 30,
        },
    },
    "import": {
        "dir": "",
    },
    "audition": {
        "volume": 0.2,
    },
    "manager": {
        "keys": dict(keymap.DEFAULTS["manager"]),
    },
    "simple": {
        "order": "shuffle",
        "keys": dict(keymap.DEFAULTS["simple"]),
    },
    "player": {
        "volume": 0.2,
        "order": "shuffle",
        "remember_progress": True,
        "keys": dict(keymap.DEFAULTS["player"]),
        "last_playlist": None,
        "last_md5": None,
        "last_position_ms": 0,
    },
}


def defaults() -> dict[str, Any]:
    """出厂默认值。

    语言与外观不是写死的常量：第一次启动按系统语言与系统主题定一次，之后
    以配置文件里的值为准。
    """
    data = copy.deepcopy(DEFAULTS)
    data["common"]["theme"] = theme_tool.system_theme()
    data["common"]["language"] = i18n.initial_language()
    return data


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _choice(value: Any, allowed: tuple[str, ...], fallback: str) -> str:
    return value if isinstance(value, str) and value in allowed else fallback


def _bool(value: Any, fallback: bool) -> bool:
    return value if isinstance(value, bool) else fallback


def _text(value: Any, fallback: str = "") -> str:
    return value.strip() if isinstance(value, str) else fallback


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _days(value: Any) -> int:
    """日志保留天数夹到 1–365；读不出数字就回退默认值。"""
    if isinstance(value, bool):
        return logging_setup.DEFAULT_RETENTION_DAYS
    try:
        days = int(str(value).strip())
    except (TypeError, ValueError):
        return logging_setup.DEFAULT_RETENTION_DAYS
    return max(logging_setup.MIN_RETENTION_DAYS, min(days, logging_setup.MAX_RETENTION_DAYS))


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    """取出一个分节，并保证它是对象。

    用户手改过的文件里 ``"player": 5`` 这种写法是合法的 JSON，但下面每一行都会
    在它上面取键。这里就地换回默认分节，宁可丢掉一个坏字段，也不让设置把启动拦下。
    """
    node = data.get(key)
    if not isinstance(node, dict):
        node = copy.deepcopy(DEFAULTS.get(key, {}))
        data[key] = node
    return node


def clamp(raw: dict[str, Any]) -> dict[str, Any]:
    """把任意来源的数据压成一份可用的设置。"""
    data = _merge(DEFAULTS, raw if isinstance(raw, dict) else {})

    common = _section(data, "common")
    common["theme"] = theme_tool.resolve(common.get("theme"))
    common["language"] = _choice(
        common.get("language"), tuple(i18n.available()), i18n.initial_language()
    )
    common["debug"] = _bool(common.get("debug"), False)
    # 总播放次数只有一个开关；它不进 adaptive 那一组，也不受歌单的自适应开关影响。
    common["record_total_plays"] = _bool(common.get("record_total_plays"), True)
    common["log_level"] = _choice(
        common.get("log_level"), logging_setup.LOG_LEVELS, logging_setup.DEFAULT_LEVEL
    )
    common["log_cleanup"] = _bool(common.get("log_cleanup"), True)
    common["log_retention_days"] = _days(common.get("log_retention_days"))
    adaptation = Adaptation.from_dict(common.get("adaptation"))
    adaptation.normalize()
    common["adaptation"] = adaptation.to_dict()

    import_section = _section(data, "import")
    import_section["dir"] = _text(import_section.get("dir"))
    # 音乐导入一律清元数据：旧配置里残留的 clean_audio 原样留着，但不再读取。

    audition = _section(data, "audition")
    audition_volume = audition.get("volume")
    audition["volume"] = (
        min(1.0, max(0.0, float(audition_volume)))
        if isinstance(audition_volume, (int, float))
        else 0.2
    )

    simple = _section(data, "simple")
    simple["order"] = _choice(simple.get("order"), SIMPLE_ORDERS, "shuffle")
    simple["keys"] = keymap.clamp("simple", simple.get("keys"))
    # 轻量音乐播放器不再设默认音量：音量完全交给 VLC 与系统混音器。
    simple.pop("volume", None)

    manager = _section(data, "manager")
    manager["keys"] = keymap.clamp("manager", manager.get("keys"))

    player = _section(data, "player")
    player["order"] = _choice(player.get("order"), PLAYER_ORDERS, "shuffle")
    volume = player.get("volume")
    player["volume"] = (
        min(1.0, max(0.0, float(volume))) if isinstance(volume, (int, float)) else 0.2
    )
    player["remember_progress"] = _bool(player.get("remember_progress"), True)
    player["keys"] = keymap.clamp("player", player.get("keys"))
    player["last_playlist"] = _optional_text(player.get("last_playlist"))
    player["last_md5"] = _optional_text(player.get("last_md5"))
    position = player.get("last_position_ms")
    player["last_position_ms"] = max(0, int(position)) if isinstance(position, int) else 0

    return data


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, Any] = defaults()
        self._flag_cache: dict[str, tuple[float, bool]] = {}

    def _lock_path(self) -> Path:
        return paths.lock_for(self.path)

    def _read_disk(self) -> dict[str, Any]:
        """锁内重读用；读不出来就按默认值，绝不抛异常。"""
        if not self.path.exists():
            return defaults()
        try:
            raw = atomic.read_json(self.path)
        except ConfigError:
            return defaults()
        return raw if isinstance(raw, dict) else defaults()

    def load(self) -> list[str]:
        """返回警告；设置损坏不阻断启动。"""
        if not self.path.exists():
            self.data = defaults()
            self.save()
            return []

        warnings: list[str] = []
        try:
            raw = atomic.read_json(self.path)
        except ConfigError as error:
            warnings.append(str(error))
            raw = {}
        self.data = clamp(raw)
        self._flag_cache.clear()
        return warnings

    def save(self) -> None:
        atomic.write_json(self.path, self.data)

    def reset(self) -> dict[str, Any]:
        """恢复出厂设置并落盘。语言与外观一起重置。"""
        with exclusive(self._lock_path()):
            self.data = defaults()
            atomic.write_json(self.path, self.data)
        self._flag_cache.clear()
        return self.data

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        """锁内先读盘再合并：另一个进程刚写的字段不该被内存里的旧值盖掉。"""
        with exclusive(self._lock_path()):
            self.data = clamp(_merge(self._read_disk(), patch))
            atomic.write_json(self.path, self.data)
        self._flag_cache.clear()
        return self.data

    def patch_player(self, patch: dict[str, Any]) -> dict[str, Any]:
        """只改 ``player`` 节里指定的键。

        manager 与 player 都会写这一节：manager 改默认值，player 记进度。
        整份写回会用启动时的旧值覆盖对方刚写的字段，所以必须读改写。
        """
        with exclusive(self._lock_path()):
            raw = self._read_disk()
            current = raw.get("player")
            merged = dict(current) if isinstance(current, dict) else {}
            merged.update(patch)
            self.data = clamp(_merge(raw, {"player": merged}))
            atomic.write_json(self.path, self.data)
        self._flag_cache.clear()
        return self.data

    def _cached_common_flag(self, key: str, fallback: bool) -> bool:
        """跨进程读 ``common`` 里的一个布尔开关，缓存两秒。

        这些值在逐曲判定里会被反复读：一轮扫几百首就是几百次读盘，而开关的
        语义是「下次判定就生效」，两秒的延迟看不出来。
        """
        now = time.monotonic()
        cached = self._flag_cache.get(key)
        if cached is not None and now - cached[0] < DEBUG_CACHE_SECONDS:
            return cached[1]
        try:
            raw = atomic.read_json(self.path)
        except (ConfigError, OSError):
            self._flag_cache[key] = (now, fallback)
            return fallback
        common = raw.get("common") if isinstance(raw, dict) else None
        value = common.get(key) if isinstance(common, dict) else None
        enabled = value if isinstance(value, bool) else fallback
        self._flag_cache[key] = (now, enabled)
        return enabled

    def debug_enabled(self) -> bool:
        """调试状态：为真时两个播放器都不判定也不记录自适应。"""
        return self._cached_common_flag("debug", False)

    def record_total_plays_enabled(self) -> bool:
        """总播放次数的总开关；读不出来时按「记录」处理。"""
        return self._cached_common_flag("record_total_plays", True)

    def apply_log_settings(self) -> None:
        """把日志三件套交给 ``logging_setup``。

        三个程序启动时各调一次，管理界面改完设置再调一次——所以改级别不用重启，
        写的是同一个日志文件。
        """
        default_days = logging_setup.DEFAULT_RETENTION_DAYS
        logging_setup.configure(
            level=str(self.get("common", "log_level", default=logging_setup.DEFAULT_LEVEL)),
            cleanup=bool(self.get("common", "log_cleanup", default=True)),
            retention_days=int(self.get("common", "log_retention_days", default=default_days)),
        )

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node
