"""拉起另一个入口。

manager 与 player 互相调用时只需要一个函数：用对解释器、对工作目录、失败返回
False。不等待子进程，也不判断该不该拉——那是调用方的决定。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from loguru import logger

from app import paths

_CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
_CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


def interpreter(*, console: bool) -> Path:
    """优先用项目 venv 里的解释器；开发环境下退回当前解释器。"""
    candidate = paths.PYTHON if console else paths.PYTHONW
    return candidate if candidate.exists() else Path(sys.executable)


def spawn(entry: Path, *, console: bool = False) -> bool:
    if not entry.exists():
        logger.error("入口不存在：{}", entry)
        return False
    try:
        subprocess.Popen(
            [str(interpreter(console=console)), str(entry)],
            cwd=str(paths.PROGRAM_DIR),
            close_fds=True,
            creationflags=_CREATE_NEW_PROCESS_GROUP | (_CREATE_NEW_CONSOLE if console else 0),
        )
    except OSError as error:
        logger.error("拉起 {} 失败：{}", entry.name, error)
        return False
    logger.info("已拉起：{}", entry.name)
    return True
