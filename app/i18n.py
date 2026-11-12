"""文案查表。

语言包放在 ``app/locales/{语言代码}.json``，文件名就是语言代码。
查不到键时依次回退到默认语言、键名本身，绝不抛异常——界面出现一个键名
比弹一个异常好排查得多。
"""

from __future__ import annotations

import json
from pathlib import Path

from app import paths

DEFAULT_LANGUAGE = "zh-CN"

_language = DEFAULT_LANGUAGE
_cache: dict[str, dict[str, str]] = {}


def _read(language: str) -> dict[str, str]:
    if language in _cache:
        return _cache[language]
    path = paths.LOCALES_DIR / f"{language}.json"
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        data = {}
    table = {str(key): str(value) for key, value in data.items()}
    _cache[language] = table
    return table


def available_languages() -> list[tuple[str, str]]:
    """返回 ``(语言代码, 该语言自称)``，按代码排序。"""
    result: list[tuple[str, str]] = []
    for path in sorted(paths.LOCALES_DIR.glob("*.json")):
        code = path.stem
        table = _read(code)
        result.append((code, table.get("language.name", code)))
    return result


def set_language(language: str) -> str:
    global _language
    if (paths.LOCALES_DIR / f"{language}.json").is_file():
        _language = language
    return _language


def current() -> str:
    return _language


def t(key: str, **values: object) -> str:
    template = _read(_language).get(key)
    if template is None:
        template = _read(DEFAULT_LANGUAGE).get(key, key)
    if not values:
        return template
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return template


def strings() -> dict[str, str]:
    """前端一次性拿走整张表，之后不再为每个词条往返一次。"""
    return dict(_read(_language))


def locale_dir() -> Path:
    return paths.LOCALES_DIR
