"""simple 的启动、队列与播放循环。

只做编排：解析歌单、生成队列、调用播放器、记录结果。判定与记录在
``app.core.adaptation``，按键在 ``app.cli.console``，绘制在 ``app.cli.render``。
播放器通过 ``play`` / ``is_playing`` / ``stop`` 三个方法注入，测试里换成假实现，
不启动真实 VLC。
"""

from __future__ import annotations

import os
import random
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

from loguru import logger

from app import logging_setup, paths
from app.cli import console, render
from app.cli.console import Action
from app.core import adaptation
from app.core.adaptation import Params
from app.core.library import Library
from app.core.playlists import PlaylistStore
from app.core.queue import build_round, play_order
from app.core.stats import SongStats, StatsStore
from app.errors import AppError
from app.models import Music, Playlist
from app.settings import SettingsStore
from app.settings import defaults as settings_defaults
from app.system import vlc
from app.system.single_instance import SingleInstance

INSTANCE_NAME = "MusicPlayerSimple"
DEFAULT_PLAYLIST_LABEL = "默认歌单"
UNKNOWN_AUTHOR = "未知作者"
POLL_MS = 120
START_TIMEOUT_SECONDS = 5.0
END_GRACE_SECONDS = 0.4
SETTINGS_WARNING = "设置文件损坏，已使用默认值（详见日志）"


class Outcome(Enum):
    PLAYED = "played"
    SKIPPED = "skipped"
    QUIT = "quit"
    FAILED = "failed"


class Screen(Protocol):
    def show(self, state: render.NowPlaying, warning: str = "") -> None: ...

    def clear(self) -> None: ...

    def message(self, text: str) -> None: ...


@dataclass(slots=True)
class Deps:
    """播放所需的外部依赖；测试里换掉 player / keys / clock / screen 就够了。"""

    library: Library
    stats: StatsStore
    player: vlc.Player
    screen: Screen
    keys: Callable[[int], bytes | None] = console.read_key
    clock: Callable[[], float] = time.monotonic
    rng: random.Random = field(default_factory=random.Random)


# ---------- 播放循环 ----------


class Session:
    """一个进程只跑一个 Session；``run()`` 返回进程退出码。"""

    def __init__(
        self,
        deps: Deps,
        playlist: Playlist,
        params: Params,
        order: str,
        songs: Sequence[str],
        warning: str = "",
    ) -> None:
        self._deps = deps
        self._uid = playlist.uid
        self._name = playlist.name or DEFAULT_PLAYLIST_LABEL
        self._adaptation_on = playlist.adaptation.enabled
        self._params = params
        self._order = order
        self._songs = list(songs)
        self._warning = warning
        self._records: dict[str, SongStats] = {}
        self._last_sounded: str | None = None

    def run(self) -> int:
        while True:
            self._reload_records()
            queue = build_round(self._songs, self._order, self._deps.rng, self._last_sounded)
            total = len(queue)
            for index, md5 in enumerate(queue, 1):
                if self._auto_skip(md5):
                    continue
                outcome, seconds = self._play(md5, index, total)
                if outcome is Outcome.QUIT:
                    return 0
                self._remember(md5, outcome, seconds)

    # ---------- 单曲 ----------

    def _play(self, md5: str, index: int, total: int) -> tuple[Outcome, float]:
        music = self._deps.library.find_music(md5)
        if music is None:
            logger.warning("歌曲不在库里，跳过：{}", md5)
            return Outcome.FAILED, 0.0
        path = paths.music_path(md5, music.ext)
        if not path.exists():
            logger.warning("音频文件缺失，跳过：{}", path)
            return Outcome.FAILED, 0.0

        self._deps.screen.show(self._state(music, index, total), self._warning)
        started_at = self._deps.clock()
        try:
            if not self._deps.player.play(path):
                logger.warning("播放失败，跳过：{}", path)
                return Outcome.FAILED, 0.0
        except Exception:  # 单曲失败不该让整个程序退出（见 plan_simple §6）
            logger.exception("播放失败，跳过：{}", path)
            return Outcome.FAILED, 0.0

        self._last_sounded = md5
        started = False
        last_playing = started_at
        while True:
            action = console.decode(self._deps.keys(POLL_MS))
            now = self._deps.clock()
            if action is Action.QUIT:
                self._stop()
                return Outcome.QUIT, now - started_at
            if action is Action.SKIP:
                self._stop()
                return Outcome.SKIPPED, now - started_at

            try:
                playing = self._deps.player.is_playing()
            except Exception:  # 查询状态失败按「没在播」处理，让超时分支兜住
                logger.exception("查询播放状态失败")
                playing = False

            if playing:
                started = True
                last_playing = now
            elif started and now - last_playing >= END_GRACE_SECONDS:
                return Outcome.PLAYED, now - started_at
            elif not started and now - started_at >= START_TIMEOUT_SECONDS:
                logger.warning("等了 {} 秒仍未出声，跳过：{}", START_TIMEOUT_SECONDS, path)
                self._stop()
                return Outcome.FAILED, now - started_at

    def _stop(self) -> None:
        try:
            self._deps.player.stop()
        except Exception:  # 停止失败不影响切歌，VLC 关掉实例时也会自己收尾
            logger.exception("停止播放失败")

    def _state(self, music: Music, index: int, total: int) -> render.NowPlaying:
        authors = self._deps.library.music_authors(music)
        return render.NowPlaying(
            title=music.title,
            author="、".join(authors) if authors else UNKNOWN_AUTHOR,
            playlist=self._name,
            index=index,
            total=total,
            order=self._order,
            adaptation=self._adaptation_on,
        )

    # ---------- 自适应 ----------

    def _reload_records(self) -> None:
        """每轮开始读一次统计：player 同时开着时也能看到它写下的记录。"""
        if not self._adaptation_on:
            return
        try:
            self._records = self._deps.stats.load(self._uid)
        except AppError as error:
            logger.error("读取统计失败，本轮按没有记录处理：{}", error)
            self._records = {}

    def _records_for(self, md5: str) -> str:
        entry = self._records.get(md5)
        return entry.records if entry else ""

    def _auto_skip(self, md5: str) -> bool:
        if not self._adaptation_on:
            return False
        if not adaptation.should_skip(self._records_for(md5), self._params, self._deps.rng):
            return False
        logger.info("自适应跳过：{}", md5)
        try:
            self._deps.stats.mark_auto_skipped(self._uid, md5)
        except Exception:  # 统计写不进去也要继续播（见 plan_simple §6）
            logger.exception("记录自动跳过失败：{}", md5)
        return True

    def _remember(self, md5: str, outcome: Outcome, seconds: float) -> None:
        # 自适应没开就不写统计：记录只服务于自适应，用户关掉它就别再动文件。
        if not self._adaptation_on:
            return
        if outcome is Outcome.PLAYED:
            self._record(md5, skipped=False)
        elif outcome is Outcome.SKIPPED:
            self._record(md5, skipped=seconds < self._params.skip_seconds)

    def _record(self, md5: str, skipped: bool) -> None:
        try:
            self._deps.stats.record(self._uid, md5, skipped, self._params.window)
        except Exception:  # 同上：统计是附加物，不能拦住播放
            logger.exception("统计写入失败：{}", md5)
            return
        entry = self._records.get(md5) or SongStats()
        entry.records = adaptation.push(entry.records, skipped, self._params.window)
        self._records[md5] = entry


# ---------- 启动 ----------


def main() -> int:
    log_file = logging_setup.setup("simple")
    _install_excepthook()
    logger.info("simple 启动，日志：{}", log_file)

    instance = SingleInstance(INSTANCE_NAME)
    if not instance.acquire():
        logger.info("已有实例在运行，退出本次启动")
        _say("simple 已经在运行。")
        return 0

    try:
        return _run(log_file)
    except Exception:
        logger.exception("simple 运行中失败")
        _say(f"程序遇到未处理的错误，详见日志：{log_file}")
        return 2
    finally:
        instance.release()


def _run(log_file: Path) -> int:
    settings, warnings = _load_settings()
    for warning in warnings:
        logger.warning(warning)

    if not _probe_vlc():
        return 1

    library = Library(paths.LIBRARY_PATH)
    playlists = PlaylistStore(paths.PLAYLISTS_PATH)
    try:
        for warning in library.load():
            logger.warning(warning)
        for warning in playlists.load():
            logger.warning(warning)
        playlist = playlists.default()
        content = playlists.resolve(playlist.uid, library)
    except AppError as error:
        logger.error("读取音乐库或歌单失败：{}", error)
        _say(f"读取音乐库失败：{error}")
        _wait_key()
        return 1

    songs = list(dict.fromkeys(play_order(content, library)))
    if not songs:
        logger.info("默认歌单为空，退出")
        _say("默认歌单里还没有歌曲，请先在管理器中导入。")
        _wait_key()
        return 1

    order = str(settings.get("simple", "order", default="shuffle"))
    params = adaptation.params_from_dict(settings.get("common", "adaptation", default={}))
    warning = SETTINGS_WARNING if warnings else ""

    stats = StatsStore(paths.STATS_DIR)
    player = vlc.VlcPlayer()
    screen = render.Screen()
    try:
        player.open()
    except vlc.VlcUnavailable as error:
        logger.error("VLC 无法初始化：{}", error)
        _say(f"VLC 无法初始化：{error}\n请重装 VLC：{vlc.DOWNLOAD_URL}")
        _wait_key()
        return 1

    def on_close() -> None:
        logger.info("控制台被关闭，停止播放")
        player.stop()
        logger.complete()

    logger.info("开始播放：歌单 {}，共 {} 首，模式 {}", playlist.uid, len(songs), order)
    try:
        with console.ConsoleSession(on_close=on_close):
            session = Session(
                Deps(library=library, stats=stats, player=player, screen=screen),
                playlist,
                params,
                order,
                songs,
                warning,
            )
            return session.run()
    finally:
        player.close()
        screen.clear()
        logger.info("simple 退出，日志：{}", log_file)


def _load_settings() -> tuple[SettingsStore, list[str]]:
    store = SettingsStore(paths.SETTINGS_PATH)
    try:
        warnings = store.load()
    except Exception as error:  # 字段类型全错时夹取会抛，不能让设置把启动拦下
        logger.error("读取设置失败，改用默认值：{}", error)
        store.data = settings_defaults()
        return store, [f"{SETTINGS_WARNING}：{error}"]
    return store, warnings


def _probe_vlc() -> bool:
    try:
        version = vlc.probe()
    except vlc.VlcUnavailable as error:
        logger.error("VLC 不可用：{}", error)
        _say(
            f"没有找到可用的 VLC。\n请先安装 VLC：{vlc.DOWNLOAD_URL}\n装好之后重新双击 simple.bat。"
        )
        _wait_key()
        return False
    logger.info("VLC 版本：{}", version)
    return True


def _say(text: str) -> None:
    print(f"[simple] {text}")


def _wait_key() -> None:
    """等一次按键再退出：双击运行时窗口一闪而过就什么都看不到了。

    标准输入不是控制台时（被重定向、由计划任务拉起）直接返回：``getch`` 没有
    控制台可读，等下去只会把进程挂住。
    """
    if os.name != "nt" or not sys.stdin.isatty():  # pragma: no cover - 只服务 Windows
        return
    print("按任意键退出……", end="", flush=True)
    try:
        import msvcrt

        msvcrt.getch()
    except (OSError, EOFError):  # 控制台在这一瞬间被关掉，不必再等
        pass
    print()


def _install_excepthook() -> None:
    """命令行程序不弹窗：堆栈进日志，屏幕上只留一行摘要。"""

    def hook(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            return
        logger.opt(exception=(exc_type, exc_value, exc_traceback)).critical("未捕获的异常")
        print(f"\n[simple] 程序遇到未处理的错误：{exc_value}")

    sys.excepthook = hook
