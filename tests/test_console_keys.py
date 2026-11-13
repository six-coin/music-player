"""绑定表到动作的映射。"""

from __future__ import annotations

from app.cli import console


def test_ctrl_c_is_skip():
    assert console.decode(b"\x03") is console.Action.SKIP


def test_ctrl_q_is_quit():
    assert console.decode(b"\x11") is console.Action.QUIT


def test_unbound_key_does_nothing():
    assert console.decode(b"x") is None


def test_no_input_does_nothing():
    assert console.decode(None) is None
    assert console.decode(b"") is None


def test_bindings_only_hold_single_bytes():
    assert all(len(key) == 1 for key in console.BINDINGS)
