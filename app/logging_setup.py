"""日志与致命错误。

每次启动新建一个带时间戳的文件，不追加到同一份。``diagnose=False``：
默认行为会把局部变量写进日志，密钥会跟着泄露。
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

from loguru import logger

from app import i18n, paths


def setup(name: str) -> Path:
    paths.LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = paths.LOG_DIR / f"{name}_{datetime.now():%Y-%m-%d_%H-%M-%S}.log"

    logger.remove()
    logger.add(
        str(log_file),
        level="DEBUG",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=False,
        rotation="5 MB",
        retention="14 days",
        format="[{level}] [{time:YYYY-MM-DD HH:mm:ss}] {message}",
    )

    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
    return log_file


def _excepthook(exc_type, exc_value, exc_traceback) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.opt(exception=(exc_type, exc_value, exc_traceback)).critical("未捕获的异常")
    fatal(f"程序遇到未处理的错误，已记录到日志：\n{exc_value}")


def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
    logger.opt(exception=(args.exc_type, args.exc_value, args.exc_traceback)).critical(
        "线程 {} 中未捕获的异常", args.thread.name if args.thread else "未知"
    )


def fatal(message: str) -> None:
    """致命错误：刷完日志、弹窗告知、立刻退出。"""
    try:
        logger.critical(message)
        logger.complete()
    except Exception:  # 日志系统本身坏了也必须能退出
        pass

    if os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(None, str(message), i18n.t("fatal.title"), 0x10)
        except Exception:
            pass
    else:  # pragma: no cover
        print(message, file=sys.stderr)
    os._exit(1)
