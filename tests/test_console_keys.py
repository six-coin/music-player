"""绑定表到动作的映射。

控制台读的是原始字节，设置里存的是 ``Ctrl+C`` 这种写法；两边靠 ``app.keymap``
对齐。绑定表是模块级状态，每个用例都从出厂值开始，免得互相漏。
"""

from __future__ import annotations

import pytest

from app import keymap
from app.cli import console


@pytest.fixture(autouse=True)
def factory_bindings():
    console.configure()
    yield
    console.configure()


def test_ctrl_c_is_skip():
    assert console.decode(b"\x03") is console.Action.SKIP


def test_ctrl_q_is_quit():
    assert console.decode(b"\x11") is console.Action.QUIT


def test_alt_f4_is_quit():
    # 功能键是两个字节；控制台给 Alt+F4 的是 0x6B
    assert console.decode(b"\x00\x6b") is console.Action.QUIT


def test_bare_f4_is_quit_too():
    # 裸 F4 是 0x3E，同样退出：键盘/控制台版本不同时不会漏
    assert console.decode(b"\x00\x3e") is console.Action.QUIT


def test_escape_hatch_survives_custom_bindings():
    """退出键改了以后 Alt+F4 仍然能退出：控制台卡住时总得留一条路。"""
    console.configure({console.Action.SKIP: "Ctrl+N", console.Action.QUIT: "Space"})

    assert console.decode(b"\x00\x6b") is console.Action.QUIT


def test_custom_bindings_replace_the_defaults():
    console.configure({console.Action.SKIP: "Ctrl+N", console.Action.QUIT: "Space"})

    assert console.decode(b"\x0e") is console.Action.SKIP
    assert console.decode(b" ") is console.Action.QUIT
    assert console.decode(b"\x03") is None


def test_unreadable_spec_falls_back_to_the_default():
    """控制台读不到 Alt 组合与功能键：换成它们等于没有跳过键。"""
    resolved = console.configure({console.Action.SKIP: "Alt+S", console.Action.QUIT: "F9"})

    assert resolved[console.Action.SKIP] == "Ctrl+C"
    assert resolved[console.Action.QUIT] == "Ctrl+Q"


def test_two_actions_cannot_share_a_key():
    resolved = console.configure({console.Action.SKIP: "Ctrl+N", console.Action.QUIT: "Ctrl+N"})

    assert resolved[console.Action.SKIP] == "Ctrl+N"
    assert resolved[console.Action.QUIT] == "Ctrl+Q"


def test_bare_function_prefix_does_nothing():
    assert console.decode(b"\x00") is None
    assert console.decode(b"\xe0") is None


def test_unbound_key_does_nothing():
    assert console.decode(b"x") is None


def test_no_input_does_nothing():
    assert console.decode(None) is None
    assert console.decode(b"") is None


def test_bindings_are_canonical_specs():
    assert all(keymap.normalize(spec) == spec for spec in console.BINDINGS)
