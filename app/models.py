"""领域模型。

只负责数据结构、归一化与字段校验，不读写文件、不碰界面。
``to_dict()`` 只输出约定的键，JSON 结构是对外硬约定。
校验顺序固定：先 ``normalize()``，再 ``validate()``。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.errors import DataError

AUDIO_EXTS = ("mp3", "m4a")
PLAYLIST_KINDS = ("manual", "filter")
FILTER_MODES = ("include", "exclude")
FILTER_TARGETS = ("all", "music", "playlist", "tag", "author")

WINDOW_MIN = 10
WINDOW_MAX = 1000
BASE_MAX = 0.99
SKIP_SECONDS_MIN = 5
SKIP_SECONDS_MAX = 300

_HEX = set("0123456789abcdef")


def new_uid() -> str:
    """32 位十六进制标识，与 MD5 同形，便于统一校验。"""
    return uuid.uuid4().hex


def is_md5(value: object) -> bool:
    return isinstance(value, str) and len(value) == 32 and set(value) <= _HEX


def _text(value: object, label: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise DataError(f"{label} 必须是字符串")
    return value.strip()


def _integer(value: object, label: str, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise DataError(f"{label} 必须是整数")
    return value


def _number(value: object, label: str, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DataError(f"{label} 必须是数字")
    return float(value)


def _unique(items: list[str]) -> list[str]:
    """去重并保留首次出现的顺序。"""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _string_list(value: object, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise DataError(f"{label} 必须是列表")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise DataError(f"{label} 的每一项都必须是字符串")
        result.append(item.strip())
    return _unique(result)


@dataclass(slots=True)
class Author:
    uid: str
    name: str
    description: str = ""

    def normalize(self) -> None:
        self.name = self.name.strip()
        self.description = self.description.strip()

    def validate(self) -> None:
        if not is_md5(self.uid):
            raise DataError(f"作者标识不合法：{self.uid}")
        if not self.name.strip():
            raise DataError("作者名称不能为空")

    def to_dict(self) -> dict[str, Any]:
        return {"uid": self.uid, "name": self.name, "description": self.description}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Author:
        return cls(
            uid=_text(raw.get("uid"), "作者标识"),
            name=_text(raw.get("name"), "作者名称"),
            description=_text(raw.get("description"), "作者简介"),
        )


@dataclass(slots=True)
class Tag:
    uid: str
    name: str

    def normalize(self) -> None:
        self.name = self.name.strip()

    def validate(self) -> None:
        if not is_md5(self.uid):
            raise DataError(f"标签标识不合法：{self.uid}")
        if not self.name.strip():
            raise DataError("标签名称不能为空")

    def to_dict(self) -> dict[str, Any]:
        return {"uid": self.uid, "name": self.name}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Tag:
        return cls(uid=_text(raw.get("uid"), "标签标识"), name=_text(raw.get("name"), "标签名称"))


@dataclass(slots=True)
class TagGroup:
    uid: str
    name: str
    compulsory: bool = False
    unique: bool = False
    tags: list[Tag] = field(default_factory=list)

    def normalize(self) -> None:
        self.name = self.name.strip()
        self.tags = [tag for tag in self.tags if tag.name.strip()]
        for tag in self.tags:
            tag.normalize()

    def validate(self) -> None:
        if not is_md5(self.uid):
            raise DataError(f"标签组标识不合法：{self.uid}")
        if not self.name.strip():
            raise DataError("标签组名称不能为空")
        seen: set[str] = set()
        for tag in self.tags:
            tag.validate()
            if tag.uid in seen:
                raise DataError(f"标签组「{self.name}」里有重复的标签标识")
            seen.add(tag.uid)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "name": self.name,
            "compulsory": self.compulsory,
            "unique": self.unique,
            "tags": [tag.to_dict() for tag in self.tags],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TagGroup:
        raw_tags = raw.get("tags") or []
        if not isinstance(raw_tags, list):
            raise DataError("标签组的 tags 必须是列表")
        return cls(
            uid=_text(raw.get("uid"), "标签组标识"),
            name=_text(raw.get("name"), "标签组名称"),
            compulsory=bool(raw.get("compulsory", False)),
            unique=bool(raw.get("unique", False)),
            tags=[Tag.from_dict(item) for item in raw_tags],
        )


@dataclass(slots=True)
class Music:
    md5: str
    names: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    ext: str = "mp3"
    duration_ms: int = 0
    size: int = 0
    created_at: int = 0
    updated_at: int = 0

    @property
    def title(self) -> str:
        return self.names[0] if self.names else self.md5[:8]

    def normalize(self) -> None:
        self.names = _unique([name.strip() for name in self.names])
        self.authors = _unique([uid.strip() for uid in self.authors])
        self.tags = _unique([uid.strip() for uid in self.tags])
        self.ext = self.ext.strip().lower()
        self.duration_ms = max(0, self.duration_ms)
        self.size = max(0, self.size)

    def validate(self) -> None:
        if not is_md5(self.md5):
            raise DataError(f"歌曲标识不合法：{self.md5}")
        if not any(name.strip() for name in self.names):
            raise DataError("歌曲名称不能为空")
        if self.ext not in AUDIO_EXTS:
            raise DataError(f"不支持的音频格式：{self.ext}")
        for uid in self.authors + self.tags:
            if not is_md5(uid):
                raise DataError(f"歌曲「{self.title}」引用了不合法的标识：{uid}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "md5": self.md5,
            "names": list(self.names),
            "authors": list(self.authors),
            "tags": list(self.tags),
            "ext": self.ext,
            "duration_ms": self.duration_ms,
            "size": self.size,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Music:
        return cls(
            md5=_text(raw.get("md5"), "歌曲标识"),
            names=_string_list(raw.get("names"), "歌曲名称"),
            authors=_string_list(raw.get("authors"), "歌曲作者"),
            tags=_string_list(raw.get("tags"), "歌曲标签"),
            ext=_text(raw.get("ext"), "音频格式"),
            duration_ms=_integer(raw.get("duration_ms"), "时长"),
            size=_integer(raw.get("size"), "文件大小"),
            created_at=_integer(raw.get("created_at"), "导入时间"),
            updated_at=_integer(raw.get("updated_at"), "修改时间"),
        )


@dataclass(slots=True)
class Filter:
    mode: str = "include"
    target: str = "all"
    values: list[str] = field(default_factory=list)

    def normalize(self) -> None:
        self.mode = self.mode.strip().lower()
        self.target = self.target.strip().lower()
        self.values = _unique([value.strip() for value in self.values])
        if self.target == "all":
            self.values = []

    def validate(self) -> None:
        if self.mode not in FILTER_MODES:
            raise DataError(f"条件的包含方式不合法：{self.mode}")
        if self.target not in FILTER_TARGETS:
            raise DataError(f"条件的筛选对象不合法：{self.target}")
        if self.target != "all" and not self.values:
            raise DataError("筛选歌曲、歌单、标签或作者时，必须至少选一个对象")
        for value in self.values:
            if not is_md5(value):
                raise DataError(f"条件引用了不合法的标识：{value}")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"mode": self.mode, "target": self.target}
        if self.target != "all":
            payload["values"] = list(self.values)
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Filter:
        return cls(
            mode=_text(raw.get("mode"), "条件方式"),
            target=_text(raw.get("target"), "条件对象"),
            values=_string_list(raw.get("values"), "条件对象列表"),
        )


@dataclass(slots=True)
class Adaptation:
    enabled: bool = False
    window: int | None = None
    min_plays: int | None = None
    base: float | None = None
    skip_seconds: int | None = None

    def normalize(self) -> None:
        if self.window is not None:
            self.window = min(WINDOW_MAX, max(WINDOW_MIN, int(self.window)))
        upper = self.window if self.window is not None else WINDOW_MAX
        if self.min_plays is not None:
            self.min_plays = min(upper, max(0, int(self.min_plays)))
        if self.base is not None:
            self.base = min(BASE_MAX, max(0.0, float(self.base)))
        if self.skip_seconds is not None:
            self.skip_seconds = min(SKIP_SECONDS_MAX, max(SKIP_SECONDS_MIN, int(self.skip_seconds)))

    def validate(self) -> None:
        if self.window is not None and not WINDOW_MIN <= self.window <= WINDOW_MAX:
            raise DataError("记录窗口超出允许范围")
        if self.base is not None and not 0.0 <= self.base <= BASE_MAX:
            raise DataError("跳过基数超出允许范围")

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "window": self.window,
            "min_plays": self.min_plays,
            "base": self.base,
            "skip_seconds": self.skip_seconds,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> Adaptation:
        if not raw:
            return cls()
        window = raw.get("window")
        min_plays = raw.get("min_plays")
        base = raw.get("base")
        skip_seconds = raw.get("skip_seconds")
        return cls(
            enabled=bool(raw.get("enabled", False)),
            window=None if window is None else _integer(window, "记录窗口"),
            min_plays=None if min_plays is None else _integer(min_plays, "最少记录数"),
            base=None if base is None else _number(base, "跳过基数"),
            skip_seconds=None if skip_seconds is None else _integer(skip_seconds, "跳过判定秒数"),
        )


@dataclass(slots=True)
class Playlist:
    uid: str
    name: str | None = None
    builtin: bool = False
    kind: str = "manual"
    entries: list[str] = field(default_factory=list)
    filters: list[Filter] = field(default_factory=list)
    adaptation: Adaptation = field(default_factory=Adaptation)
    created_at: int = 0
    updated_at: int = 0

    def normalize(self) -> None:
        self.kind = self.kind.strip().lower()
        if self.builtin:
            self.name = None
        elif self.name is not None:
            self.name = self.name.strip()
        self.entries = _unique([entry.strip() for entry in self.entries])
        if self.kind == "manual":
            self.filters = []
        else:
            self.entries = []
        self.adaptation.normalize()

    def validate(self) -> None:
        if not is_md5(self.uid):
            raise DataError(f"歌单标识不合法：{self.uid}")
        if self.kind not in PLAYLIST_KINDS:
            raise DataError(f"歌单类型不合法：{self.kind}")
        if not self.builtin and not (self.name or "").strip():
            raise DataError("歌单名称不能为空")
        if self.kind == "manual":
            for entry in self.entries:
                if not is_md5(entry):
                    raise DataError(f"歌单「{self.title}」引用了不合法的歌曲标识")
        else:
            if not self.filters:
                raise DataError(f"歌单「{self.title}」至少需要一个条件")
            for item in self.filters:
                item.validate()
        self.adaptation.validate()

    @property
    def title(self) -> str:
        return self.name or ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "name": self.name,
            "builtin": self.builtin,
            "kind": self.kind,
            "entries": list(self.entries),
            "filters": [item.to_dict() for item in self.filters],
            "adaptation": self.adaptation.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Playlist:
        raw_filters = raw.get("filters") or []
        if not isinstance(raw_filters, list):
            raise DataError("歌单的 filters 必须是列表")
        name = raw.get("name")
        return cls(
            uid=_text(raw.get("uid"), "歌单标识"),
            name=None if name is None else _text(name, "歌单名称"),
            builtin=bool(raw.get("builtin", False)),
            kind=_text(raw.get("kind"), "歌单类型"),
            entries=_string_list(raw.get("entries"), "歌单曲目"),
            filters=[Filter.from_dict(item) for item in raw_filters],
            adaptation=Adaptation.from_dict(raw.get("adaptation")),
            created_at=_integer(raw.get("created_at"), "创建时间"),
            updated_at=_integer(raw.get("updated_at"), "修改时间"),
        )
