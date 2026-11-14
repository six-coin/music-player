"""路径推导。

本模块是全部绝对路径的唯一来源，不判断文件是否存在，也不创建目录（除了启动
时那一次数据目录搬迁）。

四类位置：

| 位置 | 内容 | 默认 |
|---|---|---|
| 程序目录 | 代码、随程序分发的示例音频 | 仓库根目录 |
| 数据目录 | 音乐库、歌单、统计、设置、播放器状态 | ``%PROGRAMDATA%\\six-coin\\music-player`` |
| 本地目录 | 日志、锁、数据目录指针 | ``%LOCALAPPDATA%\\six-coin\\music-player`` |
| 临时目录 | 清洗音频、换源的中间文件 | ``%TEMP%\\six-coin\\music-player`` |

数据目录可在设置里改，落点恒以项目代号结尾；改完在下次启动时把旧目录的内容
搬过去，指针跟着改。配置里的相对路径以数据目录为基准，与当前工作目录无关；
工作目录本身在导入本模块时就被钉在程序目录，见 :func:`use_program_dir_as_cwd`。
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


def use_program_dir_as_cwd() -> None:
    """把进程的工作目录钉在程序根目录。

    双击 ``.bat`` 时 cwd 一般已经是程序目录，但从任务栏、计划任务、另一个进程
    拉起时不一定。工作目录会悄悄影响相对路径、文件对话框与第三方库的临时文件，
    所以这里统一收口一次，之后全进程不再变。路径计算本身不依赖它——内部路径
    一律由本模块给出绝对路径。
    """
    try:
        os.chdir(PROGRAM_DIR)
    except OSError:
        # 目录被删掉或没有权限时保持原样：cwd 只是便利，不该拦住启动。
        pass


use_program_dir_as_cwd()

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
#: 「更改数据目录」留下的待搬迁标记。指针只在搬完之后才改，中途断电也不会让
#: 程序在一个空目录里找数据。
DATA_PENDING = LOCAL_DIR / "data-dir.pending"


def normalize_data_dir(raw: str, base: Path | None = None) -> Path:
    """把用户给的路径收敛成绝对路径，并保证最后一层是项目代号。

    选 ``D:\\Data`` 时实际落点是 ``D:\\Data\\music-player``；已经以项目代号
    结尾就原样用。相对路径以 ``base``（默认是默认数据目录）为基准。
    """
    text = (raw or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        text = text[1:-1].strip()
    if not text:
        return DATA_DIR_DEFAULT
    path = Path(os.path.expandvars(text)).expanduser()
    if not path.is_absolute():
        path = (base or DATA_DIR_DEFAULT) / path
    path = Path(os.path.normpath(str(path)))
    if path.name.lower() != PROJECT:
        path = path / PROJECT
    return path


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


def write_data_dir(path: Path) -> None:
    """把数据目录写进指针文件。"""
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    temp = DATA_POINTER.with_suffix(".tmp")
    temp.write_text(str(path), encoding="utf-8", newline="\n")
    os.replace(temp, DATA_POINTER)


def pending_data_dir() -> Path | None:
    """上次「更改数据目录」记下的落点；没有就是 ``None``。"""
    try:
        text = DATA_PENDING.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else None


def request_data_dir(raw: str, base: Path | None = None) -> Path:
    """记下新的数据目录，等下次启动搬过去。

    只写标记不搬文件：搬发生在下次启动、在所有业务模块打开文件之前，运行中的
    进程不会遇到「文件被搬走了」。改回当前目录时只清掉标记。
    """
    target = normalize_data_dir(raw, base)
    if target == read_data_dir():
        clear_pending_data_dir()
        return target
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    temp = DATA_PENDING.with_suffix(".tmp")
    temp.write_text(str(target), encoding="utf-8", newline="\n")
    os.replace(temp, DATA_PENDING)
    return target


def clear_pending_data_dir() -> None:
    """丢掉待搬迁标记。"""
    try:
        DATA_PENDING.unlink()
    except OSError:
        pass


def _is_nested(inner: Path, outer: Path) -> bool:
    """``inner`` 是否在 ``outer`` 里（含相等）。"""
    try:
        inner.relative_to(outer)
    except ValueError:
        return False
    return True


def _move_contents(source: Path, target: Path) -> tuple[list[str], int]:
    """把 ``source`` 里的东西搬到 ``target``。目标已有的同名项不覆盖。"""
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return [f"无法创建 {target}：{error}"], 0
    if not source.is_dir():
        return [], 0

    warnings: list[str] = []
    moved = 0
    for item in list(source.iterdir()):
        if item.suffix == ".lock":
            # 锁恒在本地目录，数据目录里的锁文件没有搬运价值。
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
            warnings.append(f"迁移 {item.name} 失败：{error}")
            continue
        moved += 1
    try:
        source.rmdir()
    except OSError:
        # 还有搬不走的文件（被占用、权限不足），目录留着即可。
        pass
    return warnings, moved


def _reconcile_data_dir() -> None:
    """启动时执行上次「更改数据目录」留下的搬迁。

    只在有 ``data-dir.pending`` 时动手：把旧目录的内容搬到新目录，再改指针。
    测试用 ``SIXCOIN_DATA_DIR`` 指定了目录，一律不碰。
    """
    global MIGRATION_WARNINGS, MIGRATED_ITEMS
    if os.environ.get(_ENV_DATA, "").strip():
        return
    target = pending_data_dir()
    if target is None:
        return
    source = read_data_dir()
    if target == source:
        clear_pending_data_dir()
        return
    if _is_nested(target, source) or _is_nested(source, target):
        MIGRATION_WARNINGS = [f"数据目录不能互相嵌套：{source} → {target}"]
        return
    try:
        MIGRATION_WARNINGS, MIGRATED_ITEMS = _move_contents(source, target)
        write_data_dir(target)
    except OSError as error:  # 指针写不下去就留在原处，下次启动再试
        MIGRATION_WARNINGS = [f"数据目录切换失败：{error}"]
        return
    clear_pending_data_dir()


#: 启动时搬迁数据的警告与条数，由 ``bootstrap.prepare()`` 取走写日志。
MIGRATION_WARNINGS: list[str] = []
MIGRATED_ITEMS = 0

_reconcile_data_dir()

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
