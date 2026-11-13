"""固定区域的绘制。

只在状态变化时整块重绘，不做逐帧刷新：逐帧刷新会闪，也会白吃 CPU。
颜色只用青（标题 / 边框）、蓝（字段名）、白（值）、灰（提示），克制、不刺眼。

中文字符占两列，方框对齐必须按显示宽度算，不能按字符数算。**东亚宽度模糊**
（``east_asian_width`` 为 ``A``）的字符也按两列算：中文环境下控制台把 ``…``
``·`` 这类字符渲染成两格，按一格算会让整行短一格，右边的竖线就歪了。
方框线本身不参与计算，它是固定宽度拼上去的。
"""

from __future__ import annotations

import sys
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TextIO

RESET = "\x1b[0m"
CYAN = "\x1b[36m"
BLUE = "\x1b[94m"
WHITE = "\x1b[97m"
GRAY = "\x1b[90m"
YELLOW = "\x1b[93m"

CLEAR = "\x1b[H\x1b[J"  # 回到左上角，清到屏幕末尾

WIDTH = 48  # 框内宽度，含左右各两个空格的内边距
INSET = 2
LABEL_WIDTH = 6  # 字段名列宽：歌单 / 模式 / 自适应 的值从同一列开始

ORDER_LABELS = {"shuffle": "随机", "list_loop": "列表循环"}


@dataclass(frozen=True, slots=True)
class NowPlaying:
    """一次重绘需要的全部信息；相等就说明屏幕不用动。"""

    title: str
    author: str
    playlist: str
    index: int
    total: int
    order: str
    adaptation: bool = False


def char_width(char: str) -> int:
    """单个字符占几列。全角、宽、东亚模糊都算两列。"""
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F", "A") else 1


def width(text: str) -> int:
    """终端显示宽度。"""
    return sum(char_width(char) for char in text)


def clip(text: str, limit: int) -> str:
    """按显示宽度截断，末尾用省略号，不把汉字切成半个。"""
    if limit <= 0:
        return ""
    if width(text) <= limit:
        return text
    kept: list[str] = []
    used = 0
    for char in text:
        step = char_width(char)
        if used + step > limit - 1:
            break
        kept.append(char)
        used += step
    return "".join(kept) + "…"


def _row(parts: Sequence[tuple[str, str]]) -> str:
    visible = sum(width(text) for text, _ in parts)
    body = "".join(f"{color}{text}{RESET}" if color else text for text, color in parts)
    padding = " " * max(0, WIDTH - visible)
    return f"{CYAN}│{RESET}{body}{padding}{CYAN}│{RESET}"


def _border(left: str, right: str) -> str:
    return f"{CYAN}{left}{'─' * WIDTH}{right}{RESET}"


def _pair(label: str, value: str, right: str = "") -> str:
    head = f"{' ' * INSET}{label}{' ' * max(0, LABEL_WIDTH - width(label))}  "
    tail = f"{right}{' ' * INSET}" if right else ""
    room = WIDTH - width(head) - width(tail) - 2
    value = clip(value, max(1, room))
    gap = WIDTH - width(head) - width(value) - width(tail)
    return _row([(head, BLUE), (value, WHITE), (" " * max(0, gap), ""), (tail, GRAY)])


def draw(state: NowPlaying, warning: str = "") -> str:
    """整屏内容；行尾统一 ``\\r\\n``，控制台里才不会出现阶梯状错位。"""
    lines: list[str] = []
    if warning:
        lines.append(f"{YELLOW}{clip(warning, WIDTH + 2)}{RESET}")
    lines.extend(
        [
            _border("┌", "┐"),
            _row([(f"{' ' * INSET}正在播放", CYAN)]),
            _row([("", "")]),
            _row([(f"{' ' * INSET}{clip(state.title, WIDTH - INSET * 2)}", WHITE)]),
            _row([(f"{' ' * INSET}{clip(state.author, WIDTH - INSET * 2)}", GRAY)]),
            _row([("", "")]),
            _pair("歌单", state.playlist, f"第 {state.index} / {state.total} 首"),
            _pair("模式", ORDER_LABELS.get(state.order, state.order)),
            _pair("自适应", "开" if state.adaptation else "关"),
            _row([("", "")]),
            _row([(f"{' ' * INSET}Ctrl+C 跳过        Ctrl+Q 退出", GRAY)]),
            _border("└", "┘"),
        ]
    )
    return "\r\n".join(lines) + "\r\n"


class Screen:
    """只在状态真的变了才重绘；同样的内容重复写会把光标刷得一闪一闪。"""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stdout
        self._last: tuple[NowPlaying, str] | None = None

    def show(self, state: NowPlaying, warning: str = "") -> None:
        key = (state, warning)
        if key == self._last:
            return
        self._last = key
        self._write(CLEAR + draw(state, warning))

    def clear(self) -> None:
        self._last = None
        self._write(CLEAR)

    def message(self, text: str) -> None:
        """启动期的普通提示：不进方框，直接一行。"""
        self._write(text + "\r\n")

    def _write(self, text: str) -> None:
        try:
            self._stream.write(text)
            self._stream.flush()
        except (OSError, ValueError):  # 控制台被关掉时写不进去，不值得因此崩掉
            pass
