"""绑定表到动作的映射。"""

from __future__ import annotations

from app.cli import console


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


def test_bare_function_prefix_does_nothing():
    assert console.decode(b"\x00") is None
    assert console.decode(b"\xe0") is None


def test_unbound_key_does_nothing():
    assert console.decode(b"x") is None


def test_no_input_does_nothing():
    assert console.decode(None) is None
    assert console.decode(b"") is None


def test_bindings_hold_one_or_two_bytes():
    assert all(len(key) in (1, 2) for key in console.BINDINGS)
