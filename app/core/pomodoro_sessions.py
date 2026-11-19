"""番茄钟的完整播放记录。

与 ``pomodoro.json`` 分开存：那份是配置与累计值，读写频繁、体量要小；这一份
只追加，一条记录代表「完整走完的一轮」。两者没有外键约束——番茄钟被删掉以后
记录还在，界面显示记录里存的 uid 本身。

写入策略与其它数据文件一致：读改写全程持文件锁，落盘走原子替换。player 是
唯一的写入方，manager 只读。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from app import paths
from app.errors import ConfigError, DataError
from app.models import _integer, _text, is_md5
from app.system import atomic
from app.system.filelock import exclusive

POMODORO_SESSION_VERSION = 1

#: 记录上限。一条约 120 字节，2000 条够几年用；再多就该由用户自己决定怎么归档，
#: 而不是让每次打开管理器都去解析一份无限长的 JSON。
MAX_SESSIONS = 2000


@dataclass(slots=True)
class SessionRecord:
    """一轮完整番茄钟。``uid`` 是番茄钟的标识，不是这条记录的标识。"""

    uid: str
    started_at: int = 0
    ended_at: int = 0
    focus_ms: int = 0
    rest_ms: int = 0

    def normalize(self) -> None:
        self.started_at = max(0, self.started_at)
        self.ended_at = max(self.started_at, self.ended_at)
        self.focus_ms = max(0, self.focus_ms)
        self.rest_ms = max(0, self.rest_ms)

    def validate(self) -> None:
        if not is_md5(self.uid):
            raise DataError(f"番茄钟标识不合法：{self.uid}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "focus_ms": self.focus_ms,
            "rest_ms": self.rest_ms,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SessionRecord:
        return cls(
            uid=_text(raw.get("uid"), "番茄钟标识"),
            started_at=_integer(raw.get("started_at"), "开始时间"),
            ended_at=_integer(raw.get("ended_at"), "结束时间"),
            focus_ms=_integer(raw.get("focus_ms"), "专注时长"),
            rest_ms=_integer(raw.get("rest_ms"), "休息时长"),
        )


class SessionLog:
    """``pomodoro-sessions.json`` 的读写。记录按时间先后排，新的在末尾。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.records: list[SessionRecord] = []
        self.warnings: list[str] = []
        self._signature: tuple[int, int] | None = None

    # ---------- 读写 ----------

    def load(self) -> list[str]:
        self.warnings = warnings = []
        records: list[SessionRecord] = []
        if not self.path.exists():
            self.records = records
            self._signature = self._stat_signature()
            return warnings
        try:
            raw = atomic.read_json(self.path)
        except ConfigError as error:
            # 记录是附加物：读不出来就当没有，不备份也不拦住程序。
            logger.warning("番茄钟播放记录读不出来：{}", error)
            warnings.append(f"番茄钟播放记录已跳过（{error}）")
            self.records = records
            self._signature = self._stat_signature()
            return warnings
        items = raw.get("sessions") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            warnings.append("番茄钟播放记录的 sessions 不是列表，已跳过")
            items = []
        for item in items:
            if not isinstance(item, dict):
                warnings.append("番茄钟播放记录格式错误，已跳过一条")
                continue
            try:
                record = SessionRecord.from_dict(item)
                record.normalize()
                record.validate()
            except DataError as error:
                warnings.append(f"番茄钟播放记录已跳过：{error}")
                continue
            records.append(record)
        self.records = records[-MAX_SESSIONS:]
        self._signature = self._stat_signature()
        return list(warnings)

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
        if self._stat_signature() != self._signature:
            self.load()

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": POMODORO_SESSION_VERSION,
            "sessions": [record.to_dict() for record in self.records],
        }

    # ---------- 追加 ----------

    def append(self, record: SessionRecord) -> None:
        record.normalize()
        record.validate()
        with exclusive(paths.lock_for(self.path)):
            # 锁内重新读盘：player 可能开了两份窗口，谁最后写都不能覆盖对方。
            fresh = SessionLog(self.path)
            fresh.load()
            records = fresh.records + [record]
            self.records = records[-MAX_SESSIONS:]
            self.save()

    # ---------- 查询 ----------

    def entries(self) -> list[SessionRecord]:
        return list(self.records)
