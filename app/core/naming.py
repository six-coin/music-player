"""文件名相关的纯函数。

两件事：把歌曲名变成合法的 Windows 文件名；从「歌名 - 作者1, 作者2」里
拆出标题与作者。都不碰文件系统。
"""

from __future__ import annotations

import re

_INVALID = '\\/:*?"<>|'
_SPACES = re.compile(r"\s+")

#: Windows 的保留设备名。带不带后缀都不能用，只能换个名字。
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{index}" for prefix in ("COM", "LPT") for index in range(1, 10)
}


def sanitize_filename(name: str, fallback: str = "未命名", max_length: int = 120) -> str:
    """去掉非法字符与首尾的点、空格，并限制长度。"""
    text = "".join("_" if char in _INVALID else char for char in name)
    text = _SPACES.sub(" ", text).strip(" .")
    if len(text) > max_length:
        text = text[:max_length].rstrip(" .")
    return text or fallback


def export_filename(title: str, authors: list[str], ext: str, max_length: int = 120) -> str:
    """导出用的「歌名 - 作者1, 作者2.后缀」。

    与 ``sanitize_filename`` 的区别是非法字符直接丢掉而不是换成下划线：导出是
    给用户看的文件，``AC/DC`` 变成 ``ACDC`` 比 ``AC_DC`` 更接近原意。控制字符、
    首尾的点与空格同样去掉；撞上保留设备名时前面补下划线。
    """
    stem = " - ".join(part for part in (title.strip(), ", ".join(authors)) if part)
    text = "".join(char for char in stem if char not in _INVALID and ord(char) >= 32)
    text = _SPACES.sub(" ", text).strip(" .")
    if len(text) > max_length:
        text = text[:max_length].rstrip(" .")
    if not text:
        text = "未命名"
    if text.split(".")[0].upper() in _RESERVED:
        text = "_" + text
    suffix = ext.lstrip(".")
    return f"{text}.{suffix}" if suffix else text


def parse_filename(stem: str) -> tuple[str, list[str]]:
    """从文件名主干拆出标题与作者；拆不出来时作者为空列表。"""
    text = stem.strip()
    if " - " not in text:
        return text, []
    title, rest = text.split(" - ", 1)
    authors = [part.strip() for part in re.split(r"[,，]", rest) if part.strip()]
    return title.strip(), authors
