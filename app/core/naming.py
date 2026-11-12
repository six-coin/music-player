"""文件名相关的纯函数。

两件事：把歌曲名变成合法的 Windows 文件名；从「歌名 - 作者1, 作者2」里
拆出标题与作者。都不碰文件系统。
"""

from __future__ import annotations

import re

_INVALID = '\\/:*?"<>|'
_SPACES = re.compile(r"\s+")


def sanitize_filename(name: str, fallback: str = "未命名", max_length: int = 120) -> str:
    """去掉非法字符与首尾的点、空格，并限制长度。"""
    text = "".join("_" if char in _INVALID else char for char in name)
    text = _SPACES.sub(" ", text).strip(" .")
    if len(text) > max_length:
        text = text[:max_length].rstrip(" .")
    return text or fallback


def parse_filename(stem: str) -> tuple[str, list[str]]:
    """从文件名主干拆出标题与作者；拆不出来时作者为空列表。"""
    text = stem.strip()
    if " - " not in text:
        return text, []
    title, rest = text.split(" - ", 1)
    authors = [part.strip() for part in re.split(r"[,，]", rest) if part.strip()]
    return title.strip(), authors
