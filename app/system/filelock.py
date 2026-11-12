"""跨进程文件锁。

player 与 simple 可能同时写同一份统计文件，读改写必须在锁内完成。
Windows 用 ``msvcrt.locking``；其它平台退化为无锁（本程序只服务 Windows）。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:  # pragma: no cover - 仅用于非 Windows 上跑单元测试
    msvcrt = None  # type: ignore[assignment]


@contextmanager
def exclusive(lock_path: Path) -> Iterator[None]:
    """对 ``lock_path`` 的第一字节加排他锁，离开时释放。"""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+b")
    try:
        if msvcrt is not None:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        yield
    finally:
        try:
            if msvcrt is not None:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            handle.close()
