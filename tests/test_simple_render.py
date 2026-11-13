"""方框绘制：对齐、截断、转义序列。"""

from __future__ import annotations

import re

from app.cli import render

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def strip(text: str) -> str:
    return ANSI.sub("", text)


def make(**overrides) -> render.NowPlaying:
    payload = {
        "title": "Experience",
        "author": "Ludovico Einaudi",
        "playlist": "默认歌单",
        "index": 3,
        "total": 37,
        "order": "shuffle",
    }
    payload.update(overrides)
    return render.NowPlaying(**payload)


def test_every_line_is_the_same_visible_width():
    lines = render.draw(make()).split("\r\n")[:-1]
    assert len(lines) == 11
    for line in lines:
        assert render.width(strip(line)) == render.WIDTH + 2


def test_each_line_resets_colors_before_ending():
    for line in render.draw(make()).split("\r\n")[:-1]:
        assert line.endswith(render.RESET)


def test_long_title_is_clipped_with_ellipsis():
    text = render.draw(make(title="很长的歌名" * 20, author="作者" * 40))
    assert "…" in text
    for line in text.split("\r\n")[:-1]:
        assert render.width(strip(line)) == render.WIDTH + 2


def test_cjk_counts_as_two_columns():
    assert render.width("默认歌单") == 8
    assert render.width("Ctrl") == 4


def test_warning_is_drawn_above_the_box():
    lines = render.draw(make(), "设置文件损坏").split("\r\n")
    assert "设置文件损坏" in strip(lines[0])
    assert strip(lines[1]).startswith("┌")


def test_mode_label_is_chinese():
    text = strip(render.draw(make(order="list_loop")))
    assert "列表循环" in text
    assert "随机" in strip(render.draw(make(order="shuffle")))


def test_screen_redraws_only_when_state_changes():
    class Stream:
        def __init__(self) -> None:
            self.writes: list[str] = []

        def write(self, text: str) -> None:
            self.writes.append(text)

        def flush(self) -> None:
            pass

    stream = Stream()
    screen = render.Screen(stream)
    screen.show(make())
    first = len(stream.writes)
    screen.show(make())
    assert len(stream.writes) == first
    screen.show(make(index=4))
    assert len(stream.writes) == first + 1
