"""文案查表。

语言包放在 ``app/locales/{语言代码}.json``，文件名就是语言代码。列表顺序就是
文件名的字典序（``en-US`` 在 ``zh-CN`` 前），**不对中文特判**。

查不到键时依次回退到 ``en-US``、键名本身，绝不抛异常——界面出现一个键名
比弹一个异常好排查得多。
"""

from __future__ import annotations

import ctypes
import json
import locale
import os
from pathlib import Path

from app import paths

#: 找不到系统语言时的回退。
FALLBACK_LANGUAGE = "en-US"

#: 语言包里的语言自称。
NAME_KEY = "language.name"

_language = FALLBACK_LANGUAGE
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


def available() -> list[str]:
    """已安装的语言代码，按文件名排序。"""
    codes = sorted(path.stem for path in paths.LOCALES_DIR.glob("*.json"))
    return codes or [FALLBACK_LANGUAGE]


def available_languages() -> list[tuple[str, str]]:
    """返回 ``(语言代码, 该语言自称)``，按代码排序。"""
    return [(code, _read(code).get(NAME_KEY) or code) for code in available()]


def language_names() -> dict[str, str]:
    return dict(available_languages())


def system_language() -> str:
    """系统界面语言，映射到已安装的语言代码；都没有就用英语。"""
    codes = available()
    candidates: list[str] = []
    if os.name == "nt":
        try:
            lcid = int(ctypes.windll.kernel32.GetUserDefaultUILanguage())
            name = locale.windows_locale.get(lcid)
            if name:
                candidates.append(name.replace("_", "-"))
        except Exception:  # 取不到系统语言时按下面的环境变量与回退处理
            pass
    raw = os.environ.get("LANG") or os.environ.get("LC_ALL") or ""
    if raw:
        candidates.append(raw.split(".")[0].replace("_", "-"))

    for code in candidates:
        if code in codes:
            return code
    for code in candidates:
        primary = code.split("-")[0].lower()
        for installed in codes:
            if installed.split("-")[0].lower() == primary:
                return installed
    return FALLBACK_LANGUAGE if FALLBACK_LANGUAGE in codes else codes[0]


def initial_language() -> str:
    """第一次启动时的界面语言：系统语言在列表里就用它，否则英语。"""
    return system_language()


def set_language(language: str) -> str:
    global _language
    if (paths.LOCALES_DIR / f"{language}.json").is_file():
        _language = language
    elif FALLBACK_LANGUAGE in available():
        _language = FALLBACK_LANGUAGE
    return _language


def current() -> str:
    return _language


def t(key: str, **values: object) -> str:
    template = _read(_language).get(key)
    if template is None:
        template = _read(FALLBACK_LANGUAGE).get(key, key)
    if not values:
        return template
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return template


def strings() -> dict[str, str]:
    """前端一次性拿走整张表，之后不再为每个词条往返一次。"""
    merged = dict(_read(FALLBACK_LANGUAGE))
    merged.update(_read(_language))
    return merged


def locale_dir() -> Path:
    return paths.LOCALES_DIR
