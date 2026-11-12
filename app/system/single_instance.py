"""单实例守卫。

用命名互斥量判断同一程序是否已经在运行。管理器用它避免两个进程同时写
``library.json``；simple 用它拒绝第二次启动。非 Windows 平台一律放行。
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

ERROR_ALREADY_EXISTS = 183
SYNCHRONIZE = 0x00100000

if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateMutexW.argtypes = (wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR)
    _kernel32.CreateMutexW.restype = wintypes.HANDLE
    _kernel32.OpenMutexW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    _kernel32.OpenMutexW.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL
else:  # pragma: no cover - 仅用于非 Windows 上跑单元测试
    _kernel32 = None


class SingleInstance:
    """持有互斥量句柄直到进程退出；句柄一关，名字就释放。"""

    def __init__(self, name: str) -> None:
        self._name = f"Local\\{name}"
        self._handle: int | None = None

    def acquire(self) -> bool:
        """拿到锁返回 True；已有同名实例在跑返回 False。"""
        if _kernel32 is None:  # pragma: no cover
            return True
        handle = _kernel32.CreateMutexW(None, False, self._name)
        if not handle:
            return True
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            _kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is not None and _kernel32 is not None:
            _kernel32.CloseHandle(self._handle)
            self._handle = None


def is_running(name: str) -> bool:
    """只探测不占用：管理器在拉起 simple 之前先问一句。"""
    if _kernel32 is None:  # pragma: no cover
        return False
    handle = _kernel32.OpenMutexW(SYNCHRONIZE, False, f"Local\\{name}")
    if not handle:
        return False
    _kernel32.CloseHandle(handle)
    return True
