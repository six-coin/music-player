"""主题解析。

设置里只存 ``light`` / ``dark``；窗口背景色与网页需要的就是这两个值。旧配置
里的 ``system`` 在读取时按当时的系统偏好定一次，之后不再随系统变化。
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


def resolve(theme: str) -> str:
    if theme == "system":
        return system_theme()
    return theme if theme in ("light", "dark") else "light"
