"""管理器的窗口装配。

入口只调用这里的 ``main()``。窗口尺寸按屏幕比例算，最小尺寸保证三栏布局
不被挤坏；背景色与网页 ``--bg`` 一致，避免首帧闪白。

关窗后如果用户点过「立即重启」，由这里在释放单实例锁之后拉起新进程。
"""

from __future__ import annotations

import ctypes
import os
import subprocess

import webview
from loguru import logger

from app import bootstrap, i18n, logging_setup, paths
from app.errors import ConfigError
from app.system import theme as theme_tool
from app.system.single_instance import SingleInstance, activate_window
from app.ui.manager.api import ManagerApi

INSTANCE_NAME = "MusicPlayerManager"
BACKGROUND = {"light": "#f0f2f5", "dark": "#14161a"}


def _screen_size() -> tuple[int, int]:
    if os.name != "nt":  # pragma: no cover
        return 1280, 800
    return ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)


def _window_box() -> tuple[int, int, tuple[int, int]]:
    screen_width, screen_height = _screen_size()
    width = max(900, int(screen_width * 0.85))
    height = max(620, int(screen_height * 0.85))
    min_width = min(1100, int(screen_width * 0.9))
    min_height = min(680, int(screen_height * 0.9))
    return min(width, screen_width), min(height, screen_height), (min_width, min_height)


def main() -> None:
    warnings = bootstrap.prepare()
    log_file = logging_setup.setup("manager")
    logger.info("管理器启动，日志：{}", log_file)
    for warning in warnings:
        logger.warning(warning)

    instance = SingleInstance(INSTANCE_NAME)
    if not instance.acquire():
        bootstrap.sync_language()
        logger.info("已有实例在运行，退出本次启动")
        _activate_existing()
        return

    api: ManagerApi | None = None
    try:
        api = _run()
    finally:
        instance.release()
    if api is not None and api.restart_requested:
        _relaunch()


def _activate_existing() -> None:
    """把已开着的管理器提到前面；提不上来只记一条日志。

    多开的意思就是「让我看到那个窗口」，窗到前台就够了。弹一个「已经打开」的
    信息框只会让人以为双击失败了。
    """
    if not activate_window(i18n.t("manager.title")):
        logger.info("已有管理器在运行，但没能把窗口提到前面")


def _relaunch() -> None:
    """释放单实例锁之后拉起一个新进程。

    数据目录的搬迁只在启动早期、所有业务模块打开文件之前发生，所以「改完目录
    重启」必须是真重启。锁在调用本函数之前已经放掉，新进程不会撞上「已经在运行」。
    """
    try:
        subprocess.Popen(
            [str(bootstrap.pythonw()), str(paths.MANAGER_ENTRY)],
            cwd=str(paths.PROGRAM_DIR),
            close_fds=True,
        )
    except OSError as error:
        logger.error("重启失败：{}", error)
        bootstrap.info(i18n.t("about.restart_failed", error=error), i18n.t("manager.title"))


def _run() -> ManagerApi | None:
    first_run = bootstrap.is_first_run()
    redirected = bootstrap.redirected_from()
    try:
        api = ManagerApi(first_run=first_run, redirected_from=redirected)
    except ConfigError as error:
        logging_setup.fatal(str(error))
        return None

    for warning in api.warnings:
        logger.warning(warning)

    width, height, min_size = _window_box()
    resolved_theme = theme_tool.resolve(str(api.settings.get("common", "theme", default="light")))

    window = webview.create_window(
        i18n.t("manager.title"),
        str(paths.UI_MANAGER_DIR / "index.html"),
        js_api=api,
        width=width,
        height=height,
        min_size=min_size,
        background_color=BACKGROUND.get(resolved_theme, BACKGROUND["light"]),
        text_select=False,
    )
    api.attach(window)
    window.events.closing += api.close

    logger.info("窗口已创建：{}×{}", width, height)
    webview.start()
    return api
