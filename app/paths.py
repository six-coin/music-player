"""路径推导。

本模块是全部绝对路径的唯一来源，不判断文件是否存在，也不创建目录。
配置里写下的相对路径一律以程序目录为基准，与当前工作目录无关。
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROGRAM_DIR = PACKAGE_DIR.parent

CONFIG_DIR = PROGRAM_DIR / "config"
LOG_DIR = PROGRAM_DIR / "logs"
ASSETS_DIR = PROGRAM_DIR / "assets"
MUSIC_DIR = ASSETS_DIR / "music"
TEMP_DIR = ASSETS_DIR / "temp"

SETTINGS_PATH = CONFIG_DIR / "settings.json"
LIBRARY_PATH = CONFIG_DIR / "library.json"
PLAYLISTS_PATH = CONFIG_DIR / "playlists.json"
PLAYER_STATE_PATH = CONFIG_DIR / "player.json"
STATS_DIR = CONFIG_DIR / "stats"

LOCALES_DIR = PACKAGE_DIR / "locales"
UI_MANAGER_DIR = PACKAGE_DIR / "ui" / "manager"
UI_PLAYER_DIR = PACKAGE_DIR / "ui" / "player"

MANAGER_ENTRY = PROGRAM_DIR / "manager.pyw"
PLAYER_ENTRY = PROGRAM_DIR / "player.pyw"
SIMPLE_ENTRY = PROGRAM_DIR / "simple.py"
PYTHONW = PROGRAM_DIR / ".venv" / "Scripts" / "pythonw.exe"
PYTHON = PROGRAM_DIR / ".venv" / "Scripts" / "python.exe"


def music_path(md5: str, ext: str) -> Path:
    """入库音频的位置：文件名就是 MD5，后缀来自记录。"""
    return MUSIC_DIR / f"{md5}.{ext}"


def stats_path(playlist_uid: str) -> Path:
    """一个歌单一份统计文件。"""
    return STATS_DIR / f"{playlist_uid}.json"


def resolve_user_path(raw: str) -> Path:
    """把配置里写下的路径解析成绝对路径，基准是程序目录而不是 cwd。"""
    text = (raw or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        text = text[1:-1]
    if os.name == "nt":  # 只有 Windows 认反斜杠；别的平台保持原样，免得把 / 也换掉
        text = text.replace("/", "\\")
    text = text.strip()
    if not text:
        return PROGRAM_DIR
    path = Path(text)
    return path if path.is_absolute() else (PROGRAM_DIR / path).resolve()
