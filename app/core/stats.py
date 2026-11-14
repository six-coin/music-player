"""自适应统计的读写。

一个歌单一份文件，写在 ``config/stats/<歌单标识>.json``。player 与 simple
可能同时写同一份，所以每次「读 → 改 → 写」都持有该歌单的锁。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from app import paths
from app.core.adaptation import push, sanitize, skip_rate
from app.errors import ConfigError
from app.system import atomic
from app.system.filelock import exclusive

STATS_VERSION = 1


@dataclass(slots=True)
class SongStats:
    records: str = ""
    auto_skipped: int = 0
    last_played_at: int = 0
    #: 完整播放次数：播放时长达到跳过阈值、且不是被切走的那一次。
    #: 与自适应判定无关，只用来回答「这首歌我完整听过几次」。
    full_plays: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": self.records,
            "auto_skipped": self.auto_skipped,
            "last_played_at": self.last_played_at,
            "full_plays": self.full_plays,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SongStats:
        records = raw.get("records")
        auto_skipped = raw.get("auto_skipped")
        last_played_at = raw.get("last_played_at")
        full_plays = raw.get("full_plays")
        return cls(
            records=sanitize(records) if isinstance(records, str) else "",
            auto_skipped=auto_skipped if isinstance(auto_skipped, int) else 0,
            last_played_at=last_played_at if isinstance(last_played_at, int) else 0,
            full_plays=max(0, full_plays) if isinstance(full_plays, int) else 0,
        )


class StatsStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def path_for(self, playlist_uid: str) -> Path:
        return self.directory / f"{playlist_uid}.json"

    def load(self, playlist_uid: str) -> dict[str, SongStats]:
        path = self.path_for(playlist_uid)
        if not path.exists():
            return {}
        raw = atomic.read_json(path)
        if not isinstance(raw, dict):
            raise ConfigError(f"统计文件结构错误：{path}")
        songs = raw.get("songs") or {}
        if not isinstance(songs, dict):
            return {}
        result: dict[str, SongStats] = {}
        for md5, value in songs.items():
            if isinstance(md5, str) and isinstance(value, dict):
                result[md5] = SongStats.from_dict(value)
        return result

    def save(self, playlist_uid: str, songs: dict[str, SongStats]) -> None:
        payload = {
            "version": STATS_VERSION,
            "playlist": playlist_uid,
            "songs": {md5: item.to_dict() for md5, item in songs.items()},
        }
        atomic.write_json(self.path_for(playlist_uid), payload)

    def record(self, playlist_uid: str, md5: str, skipped: bool, window: int) -> None:
        """一次播放结束调用一次；窗口与锁都在这里收口。

        ``skipped`` 由调用方按 ``skip_seconds`` 判定：自然播完永远是「没跳过」，
        手动切歌则看播放秒数够不够。没跳过的那一次同时累加完整播放次数。
        """
        lock_path = paths.lock_for(self.path_for(playlist_uid))
        with exclusive(lock_path):
            songs = self.load(playlist_uid)
            entry = songs.setdefault(md5, SongStats())
            entry.records = push(entry.records, skipped, window)
            if not skipped:
                entry.full_plays += 1
            entry.last_played_at = int(time.time())
            self.save(playlist_uid, songs)

    def mark_auto_skipped(self, playlist_uid: str, md5: str) -> None:
        lock_path = paths.lock_for(self.path_for(playlist_uid))
        with exclusive(lock_path):
            songs = self.load(playlist_uid)
            entry = songs.setdefault(md5, SongStats())
            entry.auto_skipped += 1
            entry.last_played_at = int(time.time())
            self.save(playlist_uid, songs)

    def reset(self, playlist_uid: str) -> None:
        lock_path = paths.lock_for(self.path_for(playlist_uid))
        with exclusive(lock_path):
            self.save(playlist_uid, {})

    def remove(self, playlist_uid: str) -> bool:
        """删掉整个歌单的统计。

        只删数据文件，不删锁文件：另一个进程可能正持有它，删掉会制造
        「同一个锁文件两个 inode」的假象，下一次读改写就绕过了互斥。
        锁文件是空的，留着不占地方。
        """
        path = self.path_for(playlist_uid)
        lock_path = paths.lock_for(path)
        with exclusive(lock_path):
            try:
                path.unlink(missing_ok=True)
                return True
            except OSError:
                logger.error("删除统计文件失败：{}", path)
                return False

    def clear_all(self) -> int:
        """删掉全部统计文件，返回删掉的份数。"""
        if not self.directory.exists():
            return 0
        removed = 0
        for file in self.directory.glob("*.json"):
            lock_path = paths.lock_for(file)
            with exclusive(lock_path):
                try:
                    file.unlink()
                    removed += 1
                except OSError:
                    logger.error("删除统计文件失败：{}", file)
        return removed

    def move_key(self, playlist_uid: str, old_md5: str, new_md5: str, window: int) -> bool:
        """换源时把统计从旧标识搬到新标识；新键已存在就按先后合并。"""
        if not self.path_for(playlist_uid).exists():
            return False
        lock_path = paths.lock_for(self.path_for(playlist_uid))
        with exclusive(lock_path):
            songs = self.load(playlist_uid)
            moved = songs.pop(old_md5, None)
            if moved is None:
                return False
            current = songs.get(new_md5)
            if current is None:
                songs[new_md5] = moved
            else:
                merged = moved.records + current.records
                if window > 0:
                    merged = merged[-window:]
                current.records = merged
                current.auto_skipped += moved.auto_skipped
                current.full_plays += moved.full_plays
                current.last_played_at = max(current.last_played_at, moved.last_played_at)
            self.save(playlist_uid, songs)
            return True

    def drop(self, playlist_uid: str, md5: str) -> bool:
        """删歌时把它的统计一并移除。"""
        if not self.path_for(playlist_uid).exists():
            return False
        lock_path = paths.lock_for(self.path_for(playlist_uid))
        with exclusive(lock_path):
            songs = self.load(playlist_uid)
            if md5 not in songs:
                return False
            del songs[md5]
            self.save(playlist_uid, songs)
            return True

    def prune(self, playlist_uid: str, valid_md5s: set[str]) -> int:
        """删掉库里已经不存在的歌，返回清理条数。"""
        lock_path = paths.lock_for(self.path_for(playlist_uid))
        with exclusive(lock_path):
            songs = self.load(playlist_uid)
            stale = [md5 for md5 in songs if md5 not in valid_md5s]
            for md5 in stale:
                del songs[md5]
            if stale:
                self.save(playlist_uid, songs)
            return len(stale)

    def summary(self, playlist_uid: str) -> dict[str, dict[str, float | int | str]]:
        """给界面用的扁平摘要：记录数、跳过数、跳过率、自动跳过次数、完整播放次数。"""
        result: dict[str, dict[str, float | int | str]] = {}
        for md5, item in self.load(playlist_uid).items():
            result[md5] = {
                "records": item.records,
                "total": len(item.records),
                "skips": item.records.count("1"),
                "rate": skip_rate(item.records),
                "auto_skipped": item.auto_skipped,
                "full_plays": item.full_plays,
                "last_played_at": item.last_played_at,
            }
        return result


def default_stats_store() -> StatsStore:
    return StatsStore(paths.STATS_DIR)
