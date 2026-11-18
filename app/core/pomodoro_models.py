"""番茄钟的数据结构、常量与纯函数。

与读写分开：这里只有 dataclass、归一化、校验与默认时长模式，``pomodoro.py``
负责文件锁与事务。拆成两个文件是为了让每个文件都留在 1000 行以内。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.errors import DataError
from app.models import _integer, _text, is_md5, new_uid

POMODORO_VERSION = 1

#: 时长模式的边界。99 段已经够表达任何一天，180 分钟是单段的合理上限。
MODE_MIN_SEGMENTS = 1
MODE_MAX_SEGMENTS = 99
SEGMENT_MIN_MINUTES = 1
SEGMENT_MAX_MINUTES = 180

#: 背景的铺放方式。前三个是「按某个方向铺满」，后两个是 object-fit 的语义。
BACKGROUND_MODES = ("stretch", "fit_width", "fit_height", "contain", "cover")
#: 番茄钟界面可选的字体，值只是键，显示名在语言包里。
FONTS = ("system", "hei", "song", "kai", "round", "mono", "serif")
#: 番茄钟里不放单曲循环：一个时段只放一首歌没有意义。
PLAY_ORDERS = ("shuffle", "list_loop")
PHASES = ("focus", "rest")
ASSET_KINDS = ("background", "ring", "environment")
BACKGROUND_KINDS = ("image", "video")
AUDIO_EXTS = ("mp3", "ogg")

VOLUME_DEFAULT = {"music": 0.5, "environment": 0.35}


def _now() -> int:
    return int(time.time())


def _ratio(value: object, fallback: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return fallback
    number = float(value)
    if number != number:  # NaN
        return fallback
    return min(1.0, max(0.0, number))


def _uid_or_none(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DataError(f"{label}必须是字符串")
    text = value.strip()
    if not text:
        return None
    if not is_md5(text):
        raise DataError(f"{label}不合法：{text}")
    return text


def _choice(value: object, allowed: tuple[str, ...], label: str, fallback: str) -> str:
    text = _text(value, label)
    if not text:
        return fallback
    if text not in allowed:
        raise DataError(f"{label}不合法：{text}")
    return text


def _in_folder(relative: str, folder: str) -> bool:
    """登记的相对路径必须正好落在指定文件夹里，不能绝对、不能带 ``..``。"""
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        return False
    return path.parent.as_posix() == folder


@dataclass(slots=True)
class DurationMode:
    """一串分钟数，偶数下标是专注，奇数下标是休息。"""

    uid: str
    name: str
    segments: list[int] = field(default_factory=list)
    created_at: int = 0
    updated_at: int = 0

    @property
    def total_minutes(self) -> int:
        return sum(self.segments)

    @property
    def summary(self) -> str:
        return "/".join(str(minute) for minute in self.segments)

    def normalize(self) -> None:
        self.name = self.name.strip()
        cleaned: list[int] = []
        for value in self.segments:
            if isinstance(value, bool) or not isinstance(value, int):
                raise DataError("时长模式的每一段都必须是整数分钟")
            cleaned.append(min(SEGMENT_MAX_MINUTES, max(SEGMENT_MIN_MINUTES, value)))
        self.segments = cleaned

    def validate(self) -> None:
        if not is_md5(self.uid):
            raise DataError(f"时长模式标识不合法：{self.uid}")
        if not self.name:
            raise DataError("时长模式名称不能为空")
        if not MODE_MIN_SEGMENTS <= len(self.segments) <= MODE_MAX_SEGMENTS:
            raise DataError("时长模式至少要有一段，且不能超过 99 段")
        for value in self.segments:
            if not SEGMENT_MIN_MINUTES <= value <= SEGMENT_MAX_MINUTES:
                raise DataError(
                    f"单段时长必须在 {SEGMENT_MIN_MINUTES}–{SEGMENT_MAX_MINUTES} 分钟之间"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "name": self.name,
            "segments": list(self.segments),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DurationMode:
        raw_segments = raw.get("segments")
        if not isinstance(raw_segments, list):
            raise DataError("时长模式的 segments 必须是列表")
        segments: list[int] = []
        for value in raw_segments:
            segments.append(_integer(value, "单段时长"))
        return cls(
            uid=_text(raw.get("uid"), "时长模式标识"),
            name=_text(raw.get("name"), "时长模式名称"),
            segments=segments,
            created_at=_integer(raw.get("created_at"), "创建时间"),
            updated_at=_integer(raw.get("updated_at"), "修改时间"),
        )


@dataclass(slots=True)
class Background:
    uid: str
    name: str
    file: str
    kind: str = "image"
    duration_ms: int = 0
    width: int = 0
    height: int = 0
    size: int = 0
    created_at: int = 0
    updated_at: int = 0

    def normalize(self) -> None:
        self.name = self.name.strip()
        self.file = self.file.strip().replace("\\", "/")
        self.kind = self.kind.strip().lower()
        self.duration_ms = max(0, self.duration_ms)
        self.width = max(0, self.width)
        self.height = max(0, self.height)
        self.size = max(0, self.size)

    def validate(self) -> None:
        if not is_md5(self.uid):
            raise DataError(f"背景标识不合法：{self.uid}")
        if not self.name:
            raise DataError("背景名称不能为空")
        if self.kind not in BACKGROUND_KINDS:
            raise DataError(f"背景类型不合法：{self.kind}")
        if not _in_folder(self.file, "pomodoro/background"):
            raise DataError("背景文件必须放在 pomodoro/background 下")
        suffix = Path(self.file).suffix.lower()
        expected = ".png" if self.kind == "image" else ".mp4"
        if suffix != expected:
            raise DataError(f"背景必须是 {expected} 文件")

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "name": self.name,
            "file": self.file,
            "kind": self.kind,
            "duration_ms": self.duration_ms,
            "width": self.width,
            "height": self.height,
            "size": self.size,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Background:
        return cls(
            uid=_text(raw.get("uid"), "背景标识"),
            name=_text(raw.get("name"), "背景名称"),
            file=_text(raw.get("file"), "背景文件"),
            kind=_text(raw.get("kind"), "背景类型") or "image",
            duration_ms=_integer(raw.get("duration_ms"), "背景时长"),
            width=_integer(raw.get("width"), "背景宽度"),
            height=_integer(raw.get("height"), "背景高度"),
            size=_integer(raw.get("size"), "背景大小"),
            created_at=_integer(raw.get("created_at"), "创建时间"),
            updated_at=_integer(raw.get("updated_at"), "修改时间"),
        )


@dataclass(slots=True)
class AudioAsset:
    """提示音与环境音共用：区别只在登记在哪个列表里。"""

    uid: str
    name: str
    file: str
    ext: str = "mp3"
    duration_ms: int = 0
    size: int = 0
    created_at: int = 0
    updated_at: int = 0

    def normalize(self) -> None:
        self.name = self.name.strip()
        self.file = self.file.strip().replace("\\", "/")
        self.ext = self.ext.strip().lower().lstrip(".")
        self.duration_ms = max(0, self.duration_ms)
        self.size = max(0, self.size)

    def validate(self) -> None:
        if not is_md5(self.uid):
            raise DataError(f"音频标识不合法：{self.uid}")
        if not self.name:
            raise DataError("音频名称不能为空")
        if self.ext not in AUDIO_EXTS:
            raise DataError(f"音频格式不合法：{self.ext}")
        path = Path(self.file)
        if path.is_absolute() or ".." in path.parts:
            raise DataError("音频文件路径不合法")
        if path.suffix.lower() != f".{self.ext}":
            raise DataError("音频后缀与登记格式不一致")

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "name": self.name,
            "file": self.file,
            "ext": self.ext,
            "duration_ms": self.duration_ms,
            "size": self.size,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AudioAsset:
        return cls(
            uid=_text(raw.get("uid"), "音频标识"),
            name=_text(raw.get("name"), "音频名称"),
            file=_text(raw.get("file"), "音频文件"),
            ext=_text(raw.get("ext"), "音频格式") or "mp3",
            duration_ms=_integer(raw.get("duration_ms"), "音频时长"),
            size=_integer(raw.get("size"), "音频大小"),
            created_at=_integer(raw.get("created_at"), "创建时间"),
            updated_at=_integer(raw.get("updated_at"), "修改时间"),
        )


@dataclass(slots=True)
class PhaseAudio:
    """一个时段的音乐设置：用哪张歌单、放不放、按什么顺序。"""

    playlist: str | None = None
    play: bool = True
    order: str = "shuffle"

    def normalize(self) -> None:
        self.playlist = (self.playlist or "").strip() or None
        self.play = bool(self.play)
        self.order = (self.order or "shuffle").strip().lower()

    def validate(self) -> None:
        if self.playlist is not None and not is_md5(self.playlist):
            raise DataError(f"歌单标识不合法：{self.playlist}")
        if self.order not in PLAY_ORDERS:
            raise DataError(f"播放顺序不合法：{self.order}")

    def to_dict(self) -> dict[str, Any]:
        return {"playlist": self.playlist, "play": self.play, "order": self.order}

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> PhaseAudio:
        if not raw:
            return cls()
        return cls(
            playlist=_uid_or_none(raw.get("playlist"), "歌单标识"),
            play=bool(raw.get("play", True)),
            order=_text(raw.get("order"), "播放顺序") or "shuffle",
        )


@dataclass(slots=True)
class Pomodoro:
    uid: str
    name: str
    description: str = ""
    duration_mode: str = ""
    background: str | None = None
    background_mode: str = "cover"
    focus: PhaseAudio = field(default_factory=lambda: PhaseAudio(play=True))
    rest: PhaseAudio = field(default_factory=lambda: PhaseAudio(play=False))
    ring: str | None = None
    environment: str | None = None
    environment_enabled: bool = False
    font: str = "system"
    created_at: int = 0
    updated_at: int = 0

    def normalize(self) -> None:
        self.name = self.name.strip()
        self.description = self.description.strip()
        self.background_mode = (self.background_mode or "cover").strip().lower()
        self.font = (self.font or "system").strip().lower()
        self.focus.normalize()
        self.rest.normalize()

    def validate(self) -> None:
        if not is_md5(self.uid):
            raise DataError(f"番茄钟标识不合法：{self.uid}")
        if not self.name:
            raise DataError("番茄钟名称不能为空")
        if not is_md5(self.duration_mode):
            raise DataError("番茄钟必须选择一个合法的时长模式")
        if self.background_mode not in BACKGROUND_MODES:
            raise DataError(f"背景铺放方式不合法：{self.background_mode}")
        if self.font not in FONTS:
            raise DataError(f"字体不合法：{self.font}")
        for value, label in (
            (self.background, "背景"),
            (self.ring, "提示音"),
            (self.environment, "环境音"),
        ):
            if value is not None and not is_md5(value):
                raise DataError(f"{label}标识不合法：{value}")
        self.focus.validate()
        self.rest.validate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "name": self.name,
            "description": self.description,
            "duration_mode": self.duration_mode,
            "background": self.background,
            "background_mode": self.background_mode,
            "focus": self.focus.to_dict(),
            "rest": self.rest.to_dict(),
            "ring": self.ring,
            "environment": self.environment,
            "environment_enabled": self.environment_enabled,
            "font": self.font,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Pomodoro:
        return cls(
            uid=_text(raw.get("uid"), "番茄钟标识"),
            name=_text(raw.get("name"), "番茄钟名称"),
            description=_text(raw.get("description"), "番茄钟描述"),
            duration_mode=_text(raw.get("duration_mode"), "时长模式"),
            background=_uid_or_none(raw.get("background"), "背景标识"),
            background_mode=_text(raw.get("background_mode"), "背景铺放方式") or "cover",
            focus=PhaseAudio.from_dict(raw.get("focus")),
            rest=PhaseAudio.from_dict(raw.get("rest")),
            ring=_uid_or_none(raw.get("ring"), "提示音标识"),
            environment=_uid_or_none(raw.get("environment"), "环境音标识"),
            environment_enabled=bool(raw.get("environment_enabled", False)),
            font=_text(raw.get("font"), "字体") or "system",
            created_at=_integer(raw.get("created_at"), "创建时间"),
            updated_at=_integer(raw.get("updated_at"), "修改时间"),
        )


@dataclass(slots=True)
class TimeStats:
    """累计时长。``sessions`` 是「完整走完一套」的次数，不是会话历史。"""

    focus_ms: int = 0
    rest_ms: int = 0
    sessions: int = 0
    last_used_at: int = 0

    @property
    def total_ms(self) -> int:
        return self.focus_ms + self.rest_ms

    def normalize(self) -> None:
        self.focus_ms = max(0, self.focus_ms)
        self.rest_ms = max(0, self.rest_ms)
        self.sessions = max(0, self.sessions)
        self.last_used_at = max(0, self.last_used_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "focus_ms": self.focus_ms,
            "rest_ms": self.rest_ms,
            "sessions": self.sessions,
            "last_used_at": self.last_used_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> TimeStats:
        if not isinstance(raw, dict):
            return cls()
        stats = cls(
            focus_ms=_integer(raw.get("focus_ms"), "专注时长"),
            rest_ms=_integer(raw.get("rest_ms"), "休息时长"),
            sessions=_integer(raw.get("sessions"), "完成次数"),
            last_used_at=_integer(raw.get("last_used_at"), "最近使用时间"),
        )
        stats.normalize()
        return stats


def _default_modes() -> list[DurationMode]:
    now = _now()
    return [
        DurationMode(
            uid=new_uid(),
            name="经典番茄",
            segments=[25, 5, 25, 5, 25, 5, 25],
            created_at=now,
            updated_at=now,
        ),
        DurationMode(
            uid=new_uid(),
            name="深度专注",
            segments=[50, 10, 50],
            created_at=now,
            updated_at=now,
        ),
    ]


def _fill_default_modes(modes: dict[str, DurationMode]) -> bool:
    if modes:
        return False
    for mode in _default_modes():
        modes[mode.uid] = mode
    return True


def _repair_references(
    modes: dict[str, DurationMode],
    backgrounds: dict[str, Background],
    rings: dict[str, AudioAsset],
    environments: dict[str, AudioAsset],
    items: dict[str, Pomodoro],
) -> bool:
    """把指向不存在资源的引用清掉；时长模式退回第一个可用模式。"""
    fallback = next(iter(modes), "")
    changed = False
    for item in items.values():
        if item.duration_mode not in modes:
            item.duration_mode = fallback
            changed = True
        if item.background is not None and item.background not in backgrounds:
            item.background = None
            changed = True
        if item.ring is not None and item.ring not in rings:
            item.ring = None
            changed = True
        if item.environment is not None and item.environment not in environments:
            item.environment = None
            item.environment_enabled = False
            changed = True
    return changed
