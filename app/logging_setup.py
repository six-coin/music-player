"""日志与致命错误。

每次启动新建一个带时间戳的文件，不追加到同一份。``diagnose=False``：
默认行为会把局部变量写进日志，密钥会跟着泄露。

``.pyw`` 进程没有控制台，所以致命错误必须弹窗。弹窗统一三段：出了什么事、
发生时间、日志在哪。

崩溃路径**不走语言包**：语言包读不出来、语言键写错、i18n 还没初始化，都恰好是
崩溃时可能发生的事；这时候再去查表，弹窗里就只剩一个键名（``fatal.unexpected``
这种）。这里的文案固定中文，属于「异常路径不本地化」的约定。
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

from loguru import logger

from app import paths

_CRASH_TITLE = "程序错误"
_CRASH_TIME = "时间"
_CRASH_LOG = "日志"

_log_file: Path | None = None


def setup(name: str) -> Path:
    global _log_file
    paths.LOG_DIR.mkdir(parents=True, exist_ok=True)
    _log_file = paths.LOG_DIR / f"{name}_{datetime.now():%Y-%m-%d_%H-%M-%S}.log"

    logger.remove()
    logger.add(
        str(_log_file),
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
    return _log_file


def log_file() -> Path | None:
    return _log_file


def _excepthook(exc_type, exc_value, exc_traceback) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.opt(exception=(exc_type, exc_value, exc_traceback)).critical("未捕获的异常")
    fatal(unexpected_text(exc_type, exc_value))


def unexpected_text(exc_type, exc_value) -> str:
    """崩溃弹窗的第一行；固定中文，不查语言包。"""
    return f"程序遇到未处理的错误：{exc_type.__name__}: {exc_value}"


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
            ctypes.windll.user32.MessageBoxW(None, crash_text(message), _CRASH_TITLE, 0x10)
        except Exception:  # 弹窗失败时只能静默退出
            pass
    os._exit(1)


def crash_text(message: str) -> str:
    """崩溃弹窗的正文：错误、时间、日志位置。"""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    where = str(_log_file or paths.LOG_DIR)
    return f"{message}\n\n{_CRASH_TIME}：{stamp}\n{_CRASH_LOG}：{where}"
