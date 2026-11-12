"""管理器的窗口装配。

入口只调用这里的 ``main()``。窗口尺寸按屏幕比例算，最小尺寸保证三栏布局
不被挤坏；背景色与网页 ``--bg`` 一致，避免首帧闪白。
"""

from __future__ import annotations

import ctypes
import os

import webview
from loguru import logger

from app import i18n, logging_setup, paths
from app.errors import ConfigError
from app.system import theme as theme_tool
from app.system.single_instance import SingleInstance
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


def _alert(message: str) -> None:
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(None, message, i18n.t("manager.title"), 0x40)
    else:  # pragma: no cover
        print(message)


def main() -> None:
    log_file = logging_setup.setup("manager")
    logger.info("管理器启动，日志：{}", log_file)

    instance = SingleInstance(INSTANCE_NAME)
    if not instance.acquire():
        logger.info("已有实例在运行，退出本次启动")
        _alert(i18n.t("manager.already_running"))
        return

    try:
        api = ManagerApi()
    except ConfigError as error:
        logging_setup.fatal(str(error))
        return

    for warning in api.warnings:
        logger.warning(warning)

    width, height, min_size = _window_box()
    resolved_theme = theme_tool.resolve(str(api.settings.get("common", "theme", default="system")))

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
