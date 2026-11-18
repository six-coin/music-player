"""方框绘制：对齐、截断、转义序列。"""

from __future__ import annotations

import re

from app.cli import render

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def strip(text: str) -> str:
    return ANSI.sub("", text)


def cells(text: str) -> int:
    """控制台实际占几格：方框线固定一格，其余按 ``render.char_width``。"""
    return sum(1 if 0x2500 <= ord(char) <= 0x257F else render.char_width(char) for char in text)


def make(**overrides) -> render.NowPlaying:
    payload = {
        "title": "Experience",
        "author": "Ludovico Einaudi",
        "playlist": "默认歌单",
        "index": 3,
        "total": 37,
        "order": "shuffle",
        "adaptation": True,
    }
    payload.update(overrides)
    return render.NowPlaying(**payload)


def test_every_line_is_the_same_width():
    lines = render.draw(make()).split("\r\n")[:-1]
    assert len(lines) == 12
    for line in lines:
        assert cells(strip(line)) == render.WIDTH + 2


def test_each_line_resets_colors_before_ending():
    for line in render.draw(make()).split("\r\n")[:-1]:
        assert line.endswith(render.RESET)


def test_long_title_is_clipped_with_ellipsis():
    text = render.draw(make(title="很长的歌名" * 20, author="作者" * 40))
    assert "…" in text
    for line in text.split("\r\n")[:-1]:
        assert cells(strip(line)) == render.WIDTH + 2


def test_long_ascii_title_keeps_the_border_in_place():
    # 复现用户截图里那首：全角歌名 + 一长串数字，截断后必须正好占满一行
    title = "弥渡山歌(PHONK)" + "1" * 71
    for line in render.draw(make(title=title)).split("\r\n")[:-1]:
        assert cells(strip(line)) == render.WIDTH + 2


def test_ambiguous_width_characters_count_as_two():
    # 中文环境里控制台把 … · 这类字符渲染成两格，按一格算会短一格
    assert render.width("…") == 2
    assert render.width("默认歌单") == 8
    assert render.width("Ctrl") == 4


def test_adaptation_state_is_shown():
    assert "自适应  开" in strip(render.draw(make(adaptation=True)))
    assert "自适应  关" in strip(render.draw(make(adaptation=False)))


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


def test_key_hint_follows_the_binding():
    """方框底部那行提示写的是实际绑定的键，不是写死的中文。"""
    text = strip(render.draw(make(skip_key="Ctrl+N", quit_key="Esc")))

    assert "Ctrl+N 跳过" in text
    assert "Esc 退出" in text
