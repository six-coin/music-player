"""路径推导。

本模块是全部绝对路径的唯一来源，不判断文件是否存在，也不创建目录。

四类位置：

| 位置 | 内容 | 默认 |
|---|---|---|
| 程序目录 | 代码、随程序分发的示例音频 | 仓库根目录 |
| 数据目录 | 音乐库、歌单、统计、设置、播放器状态 | ``%PROGRAMDATA%\\six-coin\\music-player`` |
| 本地目录 | 日志、锁、数据目录指针 | ``%LOCALAPPDATA%\\six-coin\\music-player`` |
| 临时目录 | 清洗音频、换源的中间文件 | ``%TEMP%\\six-coin\\music-player`` |

数据目录可在设置里改，指针写在本地目录；改完重启才生效。配置里的相对路径
以数据目录为基准，与当前工作目录无关。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

VENDOR = "six-coin"
PROJECT = "music-player"

PACKAGE_DIR = Path(__file__).resolve().parent
PROGRAM_DIR = PACKAGE_DIR.parent

_ENV_DATA = "SIXCOIN_DATA_DIR"
_ENV_LOCAL = "SIXCOIN_LOCAL_DIR"
_ENV_TEMP = "SIXCOIN_TEMP_DIR"


def _system_dir(variable: str, fallback: str) -> Path:
    raw = os.environ.get(variable, "").strip()
    return Path(raw) if raw else Path(fallback)


LOCAL_DIR = Path(
    os.environ.get(_ENV_LOCAL, "").strip()
    or _system_dir("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")) / VENDOR / PROJECT
)
TEMP_DIR = Path(
    os.environ.get(_ENV_TEMP, "").strip() or Path(tempfile.gettempdir()) / VENDOR / PROJECT
)
DATA_DIR_DEFAULT = _system_dir("PROGRAMDATA", "C:/ProgramData") / VENDOR / PROJECT

LOG_DIR = LOCAL_DIR / "logs"
LOCK_DIR = LOCAL_DIR / "locks"
DATA_POINTER = LOCAL_DIR / "data-dir.txt"


def read_data_dir() -> Path:
    """读数据目录指针；没设过、读不出来、不是绝对路径都回退默认值。"""
    override = os.environ.get(_ENV_DATA, "").strip()
    if override:
        return Path(override)
    try:
        text = DATA_POINTER.read_text(encoding="utf-8").strip()
    except OSError:
        return DATA_DIR_DEFAULT
    if not text:
        return DATA_DIR_DEFAULT
    path = Path(text)
    return path if path.is_absolute() else DATA_DIR_DEFAULT


DATA_DIR = read_data_dir()

#: 旧名字保留：配置与业务数据现在都在数据目录里。
CONFIG_DIR = DATA_DIR
ASSETS_DIR = PROGRAM_DIR / "assets"
MUSIC_DIR = DATA_DIR / "music"

SETTINGS_PATH = DATA_DIR / "settings.json"
LIBRARY_PATH = DATA_DIR / "library.json"
PLAYLISTS_PATH = DATA_DIR / "playlists.json"
PLAYER_STATE_PATH = DATA_DIR / "player.json"
STATS_DIR = DATA_DIR / "stats"

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


def lock_for(path: Path) -> Path:
    """某个数据文件对应的锁文件。锁放在本地目录，不跟数据混在一起。"""
    return LOCK_DIR / f"{path.parent.name}-{path.stem}.lock"


def write_data_dir(path: Path) -> None:
    """把新的数据目录写进指针文件。下次启动才生效。"""
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    temp = DATA_POINTER.with_suffix(".tmp")
    temp.write_text(str(path), encoding="utf-8", newline="\n")
    os.replace(temp, DATA_POINTER)


def resolve_user_path(raw: str) -> Path:
    """把配置里写下的路径解析成绝对路径，基准是数据目录而不是 cwd。"""
    text = (raw or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        text = text[1:-1]
    if os.name == "nt":  # 只有 Windows 认反斜杠；别的平台保持原样，免得把 / 也换掉
        text = text.replace("/", "\\")
    text = text.strip()
    if not text:
        return PROGRAM_DIR
    path = Path(text)
    return path if path.is_absolute() else (DATA_DIR / path).resolve()


def migrate_legacy() -> list[str]:
    """把旧版本留在程序目录里的数据搬到新位置。

    ``config`` 与 ``assets/music`` 都是用户数据，``assets/temp`` 是临时文件，
    直接删掉。只在目标位置还没有同名项时搬，绝不覆盖。
    """
    warnings: list[str] = []
    warnings.extend(_merge_move(PROGRAM_DIR / "config", DATA_DIR))
    warnings.extend(_merge_move(ASSETS_DIR / "music", MUSIC_DIR))
    warnings.extend(_merge_move(PROGRAM_DIR / "logs", LOG_DIR))
    legacy_temp = ASSETS_DIR / "temp"
    if legacy_temp.is_dir():
        try:
            shutil.rmtree(legacy_temp)
        except OSError as error:
            warnings.append(f"清理旧临时目录失败：{error}")
    return warnings


def _merge_move(source: Path, target: Path) -> list[str]:
    if not source.is_dir():
        return []
    warnings: list[str] = []
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return [f"无法创建 {target}：{error}"]
    for item in list(source.iterdir()):
        if item.suffix == ".lock":
            # 旧锁文件没有迁移价值，留着还会让人以为锁在数据目录里。
            try:
                item.unlink()
            except OSError:
                pass
            continue
        destination = target / item.name
        if destination.exists():
            continue
        try:
            shutil.move(str(item), str(destination))
        except OSError as error:
            warnings.append(f"迁移 {item} 失败：{error}")
    try:
        source.rmdir()
    except OSError:
        pass
    return warnings
