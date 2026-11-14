"""文案完整性。

两份语言包必须同键、同占位符：少一个键会在界面上露出键名，占位符对不上会在
切换语言后显示成半截句子。前端拼出来的动态键（``player.empty.<kind>.title``）
单独列一份，避免正则抓不到就以为覆盖了。
"""

from __future__ import annotations

import json
import re

from app import i18n, paths

PLACEHOLDER = re.compile(r"\{(\w+)\}")
UI_PAGES = ("manager", "player")


def _locale(code: str = "zh-CN") -> dict[str, str]:
    text = (paths.LOCALES_DIR / f"{code}.json").read_text(encoding="utf-8")
    return json.loads(text)


def _codes() -> list[str]:
    return [path.stem for path in sorted(paths.LOCALES_DIR.glob("*.json"))]


def test_language_name_is_the_first_key():
    for code in _codes():
        assert next(iter(_locale(code))) == "language.name", code


def test_every_locale_has_the_same_keys():
    default = set(_locale())
    for code in _codes():
        assert set(_locale(code)) == default, code


def test_placeholders_match_the_default_language():
    default = _locale()
    for code in _codes():
        table = _locale(code)
        for key, template in default.items():
            assert set(PLACEHOLDER.findall(table[key])) == set(PLACEHOLDER.findall(template)), (
                f"{code}:{key}"
            )


def test_every_markup_key_exists():
    table = _locale()
    for page in UI_PAGES:
        html = (paths.PACKAGE_DIR / "ui" / page / "index.html").read_text(encoding="utf-8")
        keys = set(re.findall(r'data-i18n="([^"]+)"', html))
        assert not sorted(keys - set(table)), page


def test_every_javascript_key_exists():
    """前端用 ``T("键")`` 写死的文案也必须在语言包里。

    以 ``.`` 或 ``_`` 结尾的是拼接前缀（``T("integrity." + key)``、
    ``T("overview.issue_" + kind)``），由 ``test_dynamic_keys_exist`` 负责。
    """
    table = _locale()
    keys: set[str] = set()
    for page in UI_PAGES:
        for path in (paths.PACKAGE_DIR / "ui" / page / "js").glob("*.js"):
            keys.update(re.findall(r'T\("([a-z][\w.]*)"', path.read_text(encoding="utf-8")))
    prefixes = tuple(key for key in keys if key.endswith((".", "_")))
    missing = sorted(key for key in keys - set(prefixes) if key not in table)
    assert not missing


def test_dynamic_keys_exist():
    """拼出来的键正则抓不到，逐个列出来对一遍。"""
    table = _locale()
    keys: list[str] = []
    for suffix in ("missing_tag", "missing_file", "orphan_file", "broken_reference"):
        keys.append(f"overview.issue_{suffix}")
    for suffix in (
        "missing_file",
        "orphan_file",
        "broken_reference",
        "tag_issue",
        "stats_residue",
        "content_mismatch",
    ):
        keys.append(f"integrity.{suffix}")
    for suffix in ("shuffle", "list_loop", "repeat_one"):
        keys.append(f"player.mode.{suffix}")
    for suffix in ("no_playlist", "no_selection", "empty_playlist", "unplayable"):
        keys.append(f"player.empty.{suffix}.title")
        keys.append(f"player.empty.{suffix}.body")
    for suffix in ("title", "created", "duration", "author"):
        keys.append(f"songs.sort_{suffix}")

    assert not [key for key in keys if key not in table]


def test_missing_key_returns_key_itself():
    i18n.set_language("zh-CN")

    assert i18n.t("no.such.key") == "no.such.key"


def test_placeholders_are_substituted():
    i18n.set_language("zh-CN")

    assert (
        i18n.t("overview.summary", songs=1, playlists=2, authors=3)
        == "1 首歌 · 2 个歌单 · 3 位作者"
    )


def test_available_languages_use_native_names():
    languages = dict(i18n.available_languages())

    assert languages["zh-CN"] == "简体中文 (中国)"
    assert languages["en-US"] == "English (United States)"


def test_unknown_language_keeps_the_current_one():
    i18n.set_language("zh-CN")

    assert i18n.set_language("xx-XX") == "zh-CN"
