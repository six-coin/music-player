"""设置读写。

读的时候夹取、不信任文件；未知键原样保留，保存时不会丢用户手写的扩展字段。
内存里保持与磁盘一致的嵌套结构，层级只有两层，没必要再拍平。
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from app.errors import ConfigError
from app.models import Adaptation
from app.system import atomic
from app.system.filelock import exclusive

THEMES = ("system", "light", "dark")
SIMPLE_ORDERS = ("shuffle", "list_loop")
PLAYER_ORDERS = ("shuffle", "list_loop", "repeat_one")

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
        "volume": 0.05,
    },
    "simple": {
        "order": "shuffle",
    },
    "player": {
        "volume": 0.8,
        "order": "shuffle",
        "remember_progress": True,
        "last_playlist": None,
        "last_md5": None,
        "last_position_ms": 0,
    },
}


def defaults() -> dict[str, Any]:
    return copy.deepcopy(DEFAULTS)


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


def clamp(raw: dict[str, Any]) -> dict[str, Any]:
    """把任意来源的数据压成一份可用的设置。"""
    data = _merge(DEFAULTS, raw if isinstance(raw, dict) else {})

    common = data["common"]
    common["theme"] = _choice(common.get("theme"), THEMES, "system")
    common["language"] = _text(common.get("language"), "zh-CN") or "zh-CN"
    common["debug"] = _bool(common.get("debug"), False)
    adaptation = Adaptation.from_dict(common.get("adaptation"))
    adaptation.normalize()
    common["adaptation"] = adaptation.to_dict()

    import_section = data["import"]
    import_section["dir"] = _text(import_section.get("dir"))
    import_section["clean_audio"] = _bool(import_section.get("clean_audio"), True)

    audition = data["audition"]
    audition_volume = audition.get("volume")
    audition["volume"] = (
        min(1.0, max(0.0, float(audition_volume)))
        if isinstance(audition_volume, (int, float))
        else 0.05
    )

    simple = data["simple"]
    simple["order"] = _choice(simple.get("order"), SIMPLE_ORDERS, "shuffle")

    player = data["player"]
    player["order"] = _choice(player.get("order"), PLAYER_ORDERS, "shuffle")
    volume = player.get("volume")
    player["volume"] = (
        min(1.0, max(0.0, float(volume))) if isinstance(volume, (int, float)) else 0.8
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

    def _lock_path(self) -> Path:
        return self.path.with_suffix(".lock")

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
        return warnings

    def save(self) -> None:
        atomic.write_json(self.path, self.data)

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        """锁内先读盘再合并：另一个进程刚写的字段不该被内存里的旧值盖掉。"""
        with exclusive(self._lock_path()):
            self.data = clamp(_merge(self._read_disk(), patch))
            atomic.write_json(self.path, self.data)
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
        return self.data

    def debug_enabled(self) -> bool:
        """跨进程实时读取调试开关：manager 可能刚改过，内存里的旧值不算数。"""
        try:
            raw = atomic.read_json(self.path)
        except (ConfigError, OSError):
            return False
        common = raw.get("common") if isinstance(raw, dict) else None
        return bool(common.get("debug")) if isinstance(common, dict) else False

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node
