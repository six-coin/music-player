"""快捷键的规范形式、默认值与控制台映射。"""

from __future__ import annotations

import pytest

from app import keymap


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Ctrl+C", "Ctrl+C"),
        ("ctrl+c", "Ctrl+C"),
        ("  CTRL + C  ", "Ctrl+C"),
        ("Ctrl+Left", "Ctrl+ArrowLeft"),
        ("Ctrl+ARROWLEFT", "Ctrl+ArrowLeft"),
        ("Shift+Ctrl+K", "Ctrl+Shift+K"),
        ("Alt+Shift+F4", "Alt+Shift+F4"),
        ("Space", "Space"),
        ("spacebar", "Space"),
        ("esc", "Escape"),
        ("Ctrl+,", "Ctrl+,"),
        ("Ctrl++", "Ctrl++"),
        ("f12", "F12"),
    ],
)
def test_normalize_accepts_the_usual_spellings(raw, expected):
    assert keymap.normalize(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "Ctrl", "Ctrl+Shift", None, 42, "Ctrl+Nope", "Hyper+K"])
def test_normalize_rejects_what_is_not_a_key(raw):
    assert keymap.normalize(raw) is None


def test_modifier_order_is_fixed():
    """设置文件里的写法必须唯一，否则同一组键会有两种拼法。"""
    assert keymap.normalize("Shift+Alt+Ctrl+K") == "Ctrl+Alt+Shift+K"


def test_pretty_shortens_arrows_and_escape():
    assert keymap.pretty("Ctrl+ArrowLeft") == "Ctrl+←"
    assert keymap.pretty("Escape") == "Esc"
    assert keymap.pretty("Ctrl++") == "Ctrl++"


def test_defaults_are_already_canonical():
    for group, table in keymap.DEFAULTS.items():
        for action, spec in table.items():
            assert keymap.normalize(spec) == spec, f"{group}.{action}"


def test_every_simple_default_is_readable_by_the_console():
    for spec in keymap.DEFAULTS["simple"].values():
        assert keymap.console_supported(spec), spec


def test_clamp_fills_missing_and_fixes_broken_entries():
    table = keymap.clamp("player", {"next": "ctrl+n", "prev": "NoSuchKey"})

    assert table["next"] == "Ctrl+N"
    assert table["prev"] == "Ctrl+ArrowLeft"
    assert table["pick_loop"] == "Ctrl+L"


def test_clamp_keeps_unknown_actions():
    table = keymap.clamp("player", {"future": "Ctrl+J"})

    assert table["future"] == "Ctrl+J"


def test_clamp_ignores_non_string_values():
    table = keymap.clamp("simple", {"skip": 5, "quit": ["Ctrl+Q"]})

    assert table["skip"] == "Ctrl+C"
    assert table["quit"] == "Ctrl+Q"


def test_console_bytes_round_trip():
    for spec in ("Ctrl+C", "Ctrl+Q", "Ctrl+N", "Space", "Enter", "Tab", "Escape", "Backspace"):
        assert keymap.from_console(keymap.console_bytes(spec)) == spec


def test_console_rejects_combinations_it_cannot_read():
    assert keymap.console_bytes("Alt+S") is None
    assert keymap.console_bytes("F9") is None
    assert keymap.console_bytes("Ctrl+Shift+K") is None
    # Ctrl+H / Ctrl+I / Ctrl+M 与退格、Tab、回车同一个字节，分不出来。
    for letter in ("H", "I", "M"):
        assert keymap.console_bytes(f"Ctrl+{letter}") is None


def test_unknown_console_input_is_none():
    assert keymap.from_console(b"x") is None
    assert keymap.from_console(b"\x00\x6b") is None
    assert keymap.from_console(b"") is None
    assert keymap.from_console(None) is None


def test_player_js_fallback_matches_the_python_defaults():
    """播放器页在桥接就绪前用自己那张兜底表；两边写岔了按键会静默失灵。"""
    from app import paths

    text = (paths.UI_PLAYER_DIR / "js" / "core.js").read_text(encoding="utf-8")
    for action, spec in keymap.DEFAULTS["player"].items():
        assert f'{action}: "{spec}"' in text, action
