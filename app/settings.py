"""设置读写。

读的时候夹取、不信任文件；未知键原样保留，保存时不会丢用户手写的扩展字段。
内存里保持与磁盘一致的嵌套结构，层级只有两层，没必要再拍平。
"""

from __future__ import annotations

import copy
import time
from pathlib import Path
from typing import Any

from app import i18n, paths
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
        "theme": "system",
        "language": "zh-CN",
        "debug": False,
        "adaptation": {
            "window": 100,
            "min_plays": 10,
            "base": 0.95,
            "skip_seconds": 30,
        },
    },
    "import": {
        "dir": "",
        "clean_audio": True,
    },
    "audition": {
        "volume": 0.2,
    },
    "simple": {
        "order": "shuffle",
        "volume": 0.2,
    },
    "player": {
        "volume": 0.2,
        "order": "shuffle",
        "remember_progress": True,
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
    # 旧配置里的 system 在这里定成当时的浅色/深色，之后不再随系统变化。
    common["theme"] = theme_tool.resolve(common.get("theme"))
    common["language"] = _choice(
        common.get("language"), tuple(i18n.available()), i18n.initial_language()
    )
    common["debug"] = _bool(common.get("debug"), False)
    adaptation = Adaptation.from_dict(common.get("adaptation"))
    adaptation.normalize()
    common["adaptation"] = adaptation.to_dict()

    import_section = _section(data, "import")
    import_section["dir"] = _text(import_section.get("dir"))
    import_section["clean_audio"] = _bool(import_section.get("clean_audio"), True)

    audition = _section(data, "audition")
    audition_volume = audition.get("volume")
    audition["volume"] = (
        min(1.0, max(0.0, float(audition_volume)))
        if isinstance(audition_volume, (int, float))
        else 0.2
    )

    simple = _section(data, "simple")
    simple["order"] = _choice(simple.get("order"), SIMPLE_ORDERS, "shuffle")
    simple_volume = simple.get("volume")
    simple["volume"] = (
        min(1.0, max(0.0, float(simple_volume))) if isinstance(simple_volume, (int, float)) else 0.2
    )

    player = _section(data, "player")
    player["order"] = _choice(player.get("order"), PLAYER_ORDERS, "shuffle")
    volume = player.get("volume")
    player["volume"] = (
        min(1.0, max(0.0, float(volume))) if isinstance(volume, (int, float)) else 0.2
    )
    player["remember_progress"] = _bool(player.get("remember_progress"), True)
    player["last_playlist"] = _optional_text(player.get("last_playlist"))
    player["last_md5"] = _optional_text(player.get("last_md5"))
    position = player.get("last_position_ms")
    player["last_position_ms"] = max(0, int(position)) if isinstance(position, int) else 0

    return data


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, Any] = defaults()
        self._debug_cache: tuple[float, bool] | None = None

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
        self._debug_cache = None
        return warnings

    def save(self) -> None:
        atomic.write_json(self.path, self.data)

    def reset(self) -> dict[str, Any]:
        """恢复出厂设置并落盘。语言与外观一起重置。"""
        with exclusive(self._lock_path()):
            self.data = defaults()
            atomic.write_json(self.path, self.data)
        self._debug_cache = None
        return self.data

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        """锁内先读盘再合并：另一个进程刚写的字段不该被内存里的旧值盖掉。"""
        with exclusive(self._lock_path()):
            self.data = clamp(_merge(self._read_disk(), patch))
            atomic.write_json(self.path, self.data)
        self._debug_cache = None
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
        self._debug_cache = None
        return self.data

    def debug_enabled(self) -> bool:
        """跨进程读取调试开关，缓存两秒。

        这个值在自动跳过判定里是逐曲调用的：一轮扫几百首就是几百次读盘，
        而调试开关的语义是「下次判定就生效」，两秒的延迟看不出来。
        """
        now = time.monotonic()
        if self._debug_cache is not None and now - self._debug_cache[0] < DEBUG_CACHE_SECONDS:
            return self._debug_cache[1]
        try:
            raw = atomic.read_json(self.path)
        except (ConfigError, OSError):
            self._debug_cache = (now, False)
            return False
        common = raw.get("common") if isinstance(raw, dict) else None
        enabled = bool(common.get("debug")) if isinstance(common, dict) else False
        self._debug_cache = (now, enabled)
        return enabled

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node
