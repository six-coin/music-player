"""歌曲级总播放次数。

和自适应统计分开存、分开算：

- 自适应是「一个歌单一文件」，跟着歌单的开关走，可以按歌、按歌单、整体清空；
- 总播放次数是「全库一份」，只受设置里那一个总开关控制，清空自适应不会动它。

计数的标准由「当时正在播放的环境」决定——在歌单里播就用那个歌单的跳过阈值，
单曲循环用全局默认阈值。判定本身在 :func:`app.core.adaptation.is_full_play`，
本模块只负责把结果记下来。
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from app import paths
from app.errors import ConfigError
from app.system import atomic
from app.system.filelock import exclusive

TOTALS_VERSION = 1


class TotalStore:
    """``totals.json``：``{"version": 1, "songs": {"<md5>": 12}}``。"""

    def __init__(self, path: Path) -> None:
        self.path = path

    # ---------- 读写 ----------

    def load(self) -> dict[str, int]:
        if not self.path.exists():
            return {}
        raw = atomic.read_json(self.path)
        if not isinstance(raw, dict):
            raise ConfigError(f"总播放统计结构错误：{self.path}")
        songs = raw.get("songs")
        if not isinstance(songs, dict):
            return {}
        result: dict[str, int] = {}
        for md5, value in songs.items():
            if isinstance(md5, str) and isinstance(value, int) and not isinstance(value, bool):
                result[md5] = max(0, value)
        return result

    def load_safe(self) -> dict[str, int]:
        """读不出来就当作没有记录：总播放次数是附加物，不该拦住播放。"""
        try:
            return self.load()
        except ConfigError as error:
            logger.error("读取总播放统计失败，按空处理：{}", error)
            return {}

    def save(self, songs: dict[str, int]) -> None:
        atomic.write_json(self.path, {"version": TOTALS_VERSION, "songs": songs})

    # ---------- 计数 ----------

    def add(self, md5: str, count: int = 1) -> int:
        """记一次播放，返回累计次数；写不进去只记日志，不打断播放。"""
        if not md5:
            return 0
        with exclusive(paths.lock_for(self.path)):
            songs = self.load_safe()
            total = songs.get(md5, 0) + max(0, int(count))
            songs[md5] = total
            try:
                self.save(songs)
            except OSError:
                logger.exception("写入总播放统计失败：{}", md5)
            return total

    def get(self, md5: str) -> int:
        return self.load_safe().get(md5, 0)

    def summary(self) -> dict[str, int]:
        """一次读盘拿全库的次数，给界面的列表用。"""
        return self.load_safe()

    # ---------- 跟随歌曲的生命周期 ----------

    def drop(self, md5: str) -> bool:
        """删歌时把它的计数一并移除。"""
        if not self.path.exists():
            return False
        with exclusive(paths.lock_for(self.path)):
            songs = self.load_safe()
            if md5 not in songs:
                return False
            del songs[md5]
            self.save(songs)
            return True

    def move_key(self, old_md5: str, new_md5: str) -> bool:
        """换源时把计数从旧标识搬到新标识；新键已存在就相加。"""
        if not self.path.exists() or old_md5 == new_md5:
            return False
        with exclusive(paths.lock_for(self.path)):
            songs = self.load_safe()
            moved = songs.pop(old_md5, None)
            if moved is None:
                return False
            songs[new_md5] = songs.get(new_md5, 0) + moved
            self.save(songs)
            return True


def default_totals_store() -> TotalStore:
    return TotalStore(paths.TOTALS_PATH)
