"""启动期的公共步骤。

每个入口（``manager.pyw``、``player.pyw``、``simple.py``）在做任何事之前调用
:func:`prepare`：建目录，并把数据目录搬迁时留下的警告交给日志。

「第一次运行」的判据是数据目录里有没有 ``settings.json``。不是管理器先启动
时，由 :func:`launch_manager` 把管理器拉起来并带上来源标记；管理器完成语言
选择后会解释一句「你打开的不是这个程序」。
"""

from __future__ import annotations

import ctypes
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

from app import i18n, paths

_MB_ICONINFORMATION = 0x00000040
_MB_SETFOREGROUND = 0x00010000


def prepare() -> list[str]:
    """建目录，返回需要写进日志的警告。"""
    warnings: list[str] = list(paths.MIGRATION["warnings"])
    if paths.MIGRATION["moved"]:
        warnings.append(f"数据目录已迁移 {paths.MIGRATION['moved']} 项到 {paths.DATA_DIR}")
    for folder in (paths.DATA_DIR, paths.LOCAL_DIR, paths.LOG_DIR, paths.LOCK_DIR):
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            warnings.append(f"无法创建 {folder}：{error}")
    return warnings


def is_first_run() -> bool:
    """数据目录里还没有设置文件，就是第一次运行。"""
    return not paths.SETTINGS_PATH.exists()


def pythonw() -> Path:
    return paths.PYTHONW if paths.PYTHONW.is_file() else Path(sys.executable)


def launch_manager(origin: str) -> bool:
    """首次运行时把管理器拉起来。``origin`` 是刚才被启动的入口名。"""
    try:
        subprocess.Popen(
            [str(pythonw()), str(paths.MANAGER_ENTRY), "--redirected-from", origin],
            cwd=str(paths.PROGRAM_DIR),
            close_fds=True,
        )
        return True
    except OSError:
        return False


def redirected_from() -> str:
    """解析 ``--redirected-from <入口名>``。没有这个参数就是正常启动。"""
    argv = sys.argv[1:]
    for index, item in enumerate(argv):
        if item == "--redirected-from" and index + 1 < len(argv):
            return argv[index + 1]
    return ""


def sync_language() -> None:
    """多开提示与崩溃弹窗要按用户选过的语言说话；读不到配置就用系统语言。

    这里直接读文件，不走 ``settings.load()``：那条路径会顺手写一份默认配置，
    把「第一次运行」标记冲掉。
    """
    i18n.set_language(current_language())


def current_language() -> str:
    """配置文件里记下的界面语言；没有或读不出来时按系统语言判定。"""
    try:
        raw = json.loads(paths.SETTINGS_PATH.read_text(encoding="utf-8"))
        language = raw["common"]["language"]
    except (OSError, ValueError, KeyError, TypeError):
        return i18n.initial_language()
    return language if isinstance(language, str) and language else i18n.initial_language()


def info(message: str, title: str = "") -> None:
    """提示框（信息图标）。多开、需要用户知道但不致命的事情用它。"""
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.MessageBoxW(
            None, str(message), title or "Music Player", _MB_ICONINFORMATION | _MB_SETFOREGROUND
        )
    except Exception:  # 弹窗失败时没有别的出口
        pass


def guard(module: str, name: str) -> None:
    """入口的最后一道防线：任何未捕获异常都变成「错误 + 时间 + 日志路径」弹窗。

    模块名而不是函数对象：入口自己 ``import`` 的时候，界面库缺失这类错误会在
    ``guard`` 之外抛出去，``.pyw`` 没有控制台，用户看到的就是「双击没反应」。
    """
    try:
        target = importlib.import_module(module)
        target.main()
    except SystemExit:
        raise
    except Exception as error:  # noqa: BLE001 - 这里就是要兜住一切
        try:
            from app import logging_setup

            logging_setup.setup(name)
            logging_setup.fatal(logging_setup.unexpected_text(type(error), error))
        except Exception:  # 连日志都起不来时只能静默退出
            os._exit(1)
