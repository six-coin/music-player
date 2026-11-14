"""主题解析。

设置里只存 ``light`` / ``dark``；窗口背景色与网页需要的就是这两个值。
系统偏好只在第一次启动时读一次（``settings.defaults()``），之后不再跟随。
"""

from __future__ import annotations

import os


def system_theme() -> str:
    """读 Windows 的「应用模式」；读不到就按浅色处理。"""
    if os.name != "nt":
        return "light"
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if value else "dark"
    except OSError:
        return "light"


def resolve(theme: object) -> str:
    """任何不是 light / dark 的值都按浅色处理。"""
    return theme if theme in ("light", "dark") else "light"
