"""播放器的窗口装配。

入口只调用这里的 ``main()``。窗口尺寸取上次关闭时的大小（夹到最小尺寸与屏幕
之间）；背景色与网页 ``--bg`` 一致，避免首帧闪白。单实例守卫放在最前面：
第二个实例只弹一句提示，不开窗口。
"""

from __future__ import annotations

import ctypes
import os

import webview
from loguru import logger

from app import bootstrap, i18n, logging_setup, paths
from app.errors import ConfigError
from app.system import theme as theme_tool
from app.system.single_instance import SingleInstance, activate_window
from app.ui.player.api import PlayerApi

INSTANCE_NAME = "MusicPlayerPlayer"
BACKGROUND = {"light": "#f0f2f5", "dark": "#14161a"}
MIN_SIZE = (760, 480)


def _screen_size() -> tuple[int, int]:
    if os.name != "nt":  # pragma: no cover
        return 1280, 800
    return ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)


def _fit(width: int, height: int) -> tuple[int, int]:
    screen_width, screen_height = _screen_size()
    return (
        min(max(MIN_SIZE[0], width), screen_width),
        min(max(MIN_SIZE[1], height), screen_height),
    )


def main() -> None:
    warnings = bootstrap.prepare()
    if bootstrap.is_first_run():
        # 第一次运行还没有配置：先把管理器拉起来做初始设置。
        bootstrap.launch_manager("player")
        return

    log_file = logging_setup.setup("player")
    logger.info("播放器启动，日志：{}", log_file)
    for warning in warnings:
        logger.warning(warning)

    instance = SingleInstance(INSTANCE_NAME)
    if not instance.acquire():
        bootstrap.sync_language()
        logger.info("已有实例在运行，退出本次启动")
        # 多开的意思就是「让我看到那个窗口」：窗到前台就够了，不弹框。
        if not activate_window(i18n.t("player.title")):
            logger.info("已有播放器在运行，但没能把窗口提到前面")
        return

    try:
        api = PlayerApi()
    except ConfigError as error:
        logging_setup.fatal(str(error))
        return

    for warning in api.warnings:
        logger.warning(warning)

    width, height = _fit(*api.window_size())
    resolved = theme_tool.resolve(str(api.settings.get("common", "theme", default="light")))
    window = webview.create_window(
        i18n.t("player.title"),
        str(paths.UI_PLAYER_DIR / "index.html"),
        js_api=api,
        width=width,
        height=height,
        min_size=MIN_SIZE,
        background_color=BACKGROUND.get(resolved, BACKGROUND["light"]),
        text_select=False,
    )
    api.attach(window)
    window.events.closing += api.on_closing

    logger.info("窗口已创建：{}×{}", width, height)
    webview.start()
