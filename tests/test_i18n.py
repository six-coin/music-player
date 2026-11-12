"""文案完整性。"""

from __future__ import annotations

import json
import re

from app import i18n, paths


def _locale() -> dict[str, str]:
    text = (paths.LOCALES_DIR / "zh-CN.json").read_text(encoding="utf-8")
    return json.loads(text)


def test_language_name_is_the_first_key():
    assert next(iter(_locale())) == "language.name"


def test_every_markup_key_exists():
    table = _locale()
    html = (paths.UI_MANAGER_DIR / "index.html").read_text(encoding="utf-8")
    keys = set(re.findall(r'data-i18n="([^"]+)"', html))

    missing = sorted(keys - set(table))
    assert not missing


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
