"""控制台输入层。

把「按键」变成「动作」：进入时关掉行输入、回显与已处理输入，于是 ``Ctrl+C``
不再触发 SIGINT，而是和别的键一样作为一个字节被读到；退出时原样恢复。

绑定表是数据而不是代码——加一个键只需在 ``BINDINGS`` 里加一行、在 ``Action``
里加一项，主循环不用动。
"""

from __future__ import annotations

import ctypes
import os
import time
from collections.abc import Callable
from enum import Enum

STD_INPUT_HANDLE = -10
STD_OUTPUT_HANDLE = -11

ENABLE_PROCESSED_INPUT = 0x0001
ENABLE_LINE_INPUT = 0x0002
ENABLE_ECHO_INPUT = 0x0004
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

CTRL_C_EVENT = 0
CTRL_BREAK_EVENT = 1
CTRL_CLOSE_EVENT = 2
CTRL_LOGOFF_EVENT = 5
CTRL_SHUTDOWN_EVENT = 6

# 关掉窗口、注销、关机：这三种都要在进程被杀掉之前停播并恢复控制台。
_EXIT_EVENTS = (CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT)

POLL_SECONDS = 0.01

if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _HANDLER = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)
else:  # pragma: no cover - 仅用于非 Windows 上跑单元测试
    _kernel32 = None
    _HANDLER = None


class Action(Enum):
    SKIP = "skip"
    QUIT = "quit"


BINDINGS: dict[bytes, Action] = {
    b"\x03": Action.SKIP,  # Ctrl+C
    b"\x11": Action.QUIT,  # Ctrl+Q
    # 关掉 ENABLE_PROCESSED_INPUT 之后 Alt+F4 不再由窗口处理，而是当按键送进来：
    # 功能键是两字节（0x00 + 码），控制台给 Alt+F4 的是 0x6B、裸 F4 是 0x3E。
    # 两个都绑上，免得键盘/控制台版本不同时漏掉。
    b"\x00\x6b": Action.QUIT,  # Alt+F4
    b"\x00\x3e": Action.QUIT,  # F4
}

# 功能键（F1–F12、方向键等）的 getch 前缀：第一个字节是 0x00 或 0xE0。
_FUNCTION_PREFIXES = (b"\x00", b"\xe0")


def decode(chunk: bytes | None) -> Action | None:
    """把一个输入块翻成动作；没绑定就返回 None。"""
    if not chunk:
        return None
    action = BINDINGS.get(chunk)
    if action is not None:
        return action
    return BINDINGS.get(chunk[:1])


def read_key(timeout_ms: int = 0) -> bytes | None:
    """最多等 ``timeout_ms`` 毫秒；没按键返回 None，不阻塞主循环。

    功能键是两个字节（前缀 + 扫描码），一次读齐再返回，否则第二个字节会被
    当成单独的一次按键。
    """
    if os.name != "nt":  # pragma: no cover - 只服务 Windows
        time.sleep(max(0, timeout_ms) / 1000)
        return None

    import msvcrt

    deadline = time.monotonic() + max(0, timeout_ms) / 1000
    while True:
        try:
            if msvcrt.kbhit():
                chunk = msvcrt.getch()
                if chunk in _FUNCTION_PREFIXES and msvcrt.kbhit():
                    chunk += msvcrt.getch()
                return chunk
        except OSError:  # 标准输入被重定向时没有控制台可读，退化为一直没按键
            time.sleep(max(0, timeout_ms) / 1000)
            return None
        if time.monotonic() >= deadline:
            return None
        time.sleep(POLL_SECONDS)


def _get_mode(handle: int) -> int | None:
    mode = ctypes.c_uint()
    if not _kernel32.GetConsoleMode(handle, ctypes.byref(mode)):  # type: ignore[union-attr]
        return None
    return mode.value


def _set_mode(handle: int, mode: int) -> None:
    _kernel32.SetConsoleMode(handle, mode)  # type: ignore[union-attr]


class ConsoleSession:
    """进入时接管控制台，退出时原样还原；异常、Ctrl+Q、关窗口都要走到还原。"""

    def __init__(self, on_close: Callable[[], None] | None = None) -> None:
        self._on_close = on_close
        self._stdin_mode: int | None = None
        self._stdout_mode: int | None = None
        self._handler: object | None = None
        self._stdin: int | None = None

    # ---------- 上下文管理 ----------

    def __enter__(self) -> ConsoleSession:
        self._enter()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._leave()

    # ---------- 内部 ----------

    def _enter(self) -> None:
        if _kernel32 is None:  # pragma: no cover - 只服务 Windows
            return

        stdin = _kernel32.GetStdHandle(STD_INPUT_HANDLE)
        mode = _get_mode(stdin)
        if mode is not None:
            self._stdin = stdin
            self._stdin_mode = mode
            # 关掉这三个标志后，Ctrl+C 不再变成 SIGINT，而是普通输入字节。
            _set_mode(
                stdin,
                mode & ~(ENABLE_LINE_INPUT | ENABLE_ECHO_INPUT | ENABLE_PROCESSED_INPUT),
            )

        stdout = _kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        out_mode = _get_mode(stdout)
        if out_mode is not None:
            self._stdout_mode = out_mode
            _set_mode(stdout, out_mode | ENABLE_VIRTUAL_TERMINAL_PROCESSING)

        if _HANDLER is not None:
            self._handler = _HANDLER(self._handle_event)
            _kernel32.SetConsoleCtrlHandler(self._handler, True)

    def _leave(self) -> None:
        if _kernel32 is None:  # pragma: no cover - 只服务 Windows
            return

        if self._handler is not None:
            _kernel32.SetConsoleCtrlHandler(self._handler, False)
            self._handler = None
        if self._stdin is not None and self._stdin_mode is not None:
            _set_mode(self._stdin, self._stdin_mode)
            self._stdin = None
            self._stdin_mode = None
        if self._stdout_mode is not None:
            _set_mode(_kernel32.GetStdHandle(STD_OUTPUT_HANDLE), self._stdout_mode)
            self._stdout_mode = None

    def _handle_event(self, event: int) -> int:
        """控制台事件回调：在系统线程里执行，只做停播、还原、刷日志。"""
        if event not in _EXIT_EVENTS:
            return 0
        if self._on_close is not None:
            try:
                self._on_close()
            except Exception:  # 退出路径上不能再抛，否则系统会弹「异常终止」
                pass
        self._leave()
        return 1
