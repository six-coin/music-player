"""把文件送进 Windows 回收站。

用 ``SHFileOperationW`` + ``FOF_ALLOWUNDO``，这是资源管理器里「删除」走的同一条路，
用户能从回收站还原。非 Windows 平台直接删——这个程序只服务 Windows，不做分支兼容，
但测试跑在什么平台上都得能过，所以保留一个明确的降级路径。
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

from loguru import logger

FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400


class _SHFileOpStructW(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("wFunc", ctypes.c_uint),
        ("pFrom", ctypes.c_wchar_p),
        ("pTo", ctypes.c_wchar_p),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", ctypes.c_int),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", ctypes.c_wchar_p),
    ]


def _recycle_windows(path: Path) -> bool:
    # pFrom 必须是「双 null 结尾」的多字符串；ctypes 会保留字符串里的内嵌 \0。
    payload = f"{path}\0\0"
    operation = _SHFileOpStructW()
    operation.wFunc = FO_DELETE
    operation.pFrom = payload
    operation.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    try:
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    except Exception as error:  # 没有 shell32 或调用失败都走降级
        logger.error("调用回收站失败：{}", error)
        return False
    if result != 0:
        logger.error("回收站返回错误码 {}：{}", result, path)
        return False
    return not operation.fAnyOperationsAborted


def _delete_plain(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except OSError as error:
        logger.error("删除文件失败：{}", error)
        return False


def recycle(path: Path) -> bool:
    """把单个文件送入回收站；失败时退化成直接删除。"""
    target = Path(path)
    if not target.exists():
        return True
    if sys.platform != "win32":
        return _delete_plain(target)
    if _recycle_windows(target):
        return True
    return _delete_plain(target)


def _free_name(directory: Path, stem: str, suffix: str) -> Path:
    candidate = directory / f"{stem}{suffix}"
    index = 2
    while candidate.exists():
        candidate = directory / f"{stem} ({index}){suffix}"
        index += 1
    return candidate


def recycle_as(path: Path, display_name: str) -> bool:
    """先改名再送回收站，这样在回收站里看到的是歌名而不是 MD5。"""
    target = Path(path)
    if not target.exists():
        return True
    stem = (display_name or "").strip() or target.stem
    renamed = _free_name(target.parent, stem, target.suffix)
    try:
        os.replace(target, renamed)
    except OSError as error:
        logger.warning("重命名失败，按原名删除：{}", error)
        renamed = target
    return recycle(renamed)
