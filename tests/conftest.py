"""测试公共设施：固定语言，提供构造歌曲的工厂与 simple 的假依赖。"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from app import i18n, paths
from app.cli.simple import Deps, Session
from app.core.adaptation import Params
from app.core.library import Library
from app.core.stats import StatsStore
from app.models import Adaptation, Music, Playlist


@pytest.fixture(autouse=True)
def fixed_language():
    i18n.set_language("zh-CN")
    yield
    i18n.set_language("zh-CN")


@pytest.fixture(autouse=True)
def isolated_media(tmp_path_factory, monkeypatch):
    """测试绝不碰真实的 assets 目录：用户库里的音频不该被测试删掉或数成孤儿。"""
    root = tmp_path_factory.mktemp("media")
    monkeypatch.setattr(paths, "ASSETS_DIR", root)
    monkeypatch.setattr(paths, "MUSIC_DIR", root / "music")
    monkeypatch.setattr(paths, "TEMP_DIR", root / "temp")
    yield root


@pytest.fixture
def music_factory():
    def build(char: str = "a", **overrides) -> Music:
        payload = {
            "md5": char * 32,
            "names": [f"Song {char}"],
            "authors": [],
            "tags": [],
            "ext": "mp3",
            "duration_ms": 1000,
            "size": 100,
            "created_at": 1,
            "updated_at": 1,
        }
        payload.update(overrides)
        return Music(**payload)

    return build


# ---------- simple 的假依赖 ----------


class FakePlayer:
    """按轮询次数模拟「在播 → 播完」，不启动 VLC、不 sleep。"""

    def __init__(self, polls: int = 3) -> None:
        self.polls = polls
        self.played: list[Path] = []
        self.stops = 0
        self.fail = False
        self.fail_first = False
        self._left = 0

    def play(self, path: Path) -> bool:
        self.played.append(Path(path))
        self._left = self.polls
        if self.fail or (self.fail_first and len(self.played) == 1):
            return False
        return True

    def is_playing(self) -> bool:
        if self._left <= 0:
            return False
        self._left -= 1
        return True

    def stop(self) -> None:
        self.stops += 1
        self._left = 0


class FakeClock:
    """每次读表前进一格，把「等 30 秒」压缩成几次调用。"""

    def __init__(self, step: float = 0.1) -> None:
        self.step = step
        self.now = 0.0

    def __call__(self) -> float:
        self.now += self.step
        return self.now


class FakeKeys:
    """第 N 次轮询返回预设按键；默认一直没按键。

    ``max_calls`` 是防挂死的保险：脚本写错时以「退出」收场，让断言去失败，
    而不是让整个测试套件卡住。
    """

    def __init__(self, skip_at: int | None = None, quit_at: int | None = None) -> None:
        self.skip_at = skip_at
        self.quit_at = quit_at
        self.calls = 0
        self.max_calls = 5000

    def __call__(self, timeout_ms: int) -> bytes | None:
        self.calls += 1
        if self.skip_at is not None and self.calls == self.skip_at:
            return b"\x03"
        if self.quit_at is not None and self.calls == self.quit_at:
            return b"\x11"
        if self.calls > self.max_calls:
            return b"\x11"
        return None


class FakeScreen:
    def __init__(self) -> None:
        self.states: list[object] = []
        self.warnings: list[str] = []
        self.cleared = 0

    def show(self, state, warning: str = "") -> None:
        self.states.append(state)
        self.warnings.append(warning)

    def clear(self) -> None:
        self.cleared += 1

    def message(self, text: str) -> None:
        pass


class SimpleEnv:
    """一套 simple 运行环境：真库、真统计文件、假播放器 / 假时钟 / 假按键。"""

    def __init__(self, root: Path) -> None:
        self.library = Library(root / "library.json")
        self.stats = StatsStore(root / "stats")
        self.playlist = Playlist(
            uid="f" * 32,
            name=None,
            builtin=True,
            kind="filter",
            # 大部分用例断言的是「记录写了什么」，所以默认打开自适应；
            # 关掉的场景在用例里显式改成 False。
            adaptation=Adaptation(enabled=True),
        )
        self.player = FakePlayer()
        self.keys = FakeKeys()
        self.clock = FakeClock()
        self.screen = FakeScreen()
        self.rng = random.Random(7)
        self.songs: list[str] = []
        self.params = Params(window=100, min_plays=10, base=0.95, skip_seconds=30)

    def add(self, char: str, title: str | None = None) -> str:
        """往库里加一首歌，并在磁盘上放一个占位音频。"""
        md5 = char * 32
        self.library.musics[md5] = Music(
            md5=md5, names=[title or f"Song {char}"], ext="mp3", duration_ms=1000
        )
        path = paths.music_path(md5, "mp3")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake")
        self.songs.append(md5)
        return md5

    def records(self, md5: str) -> str:
        entry = self.stats.load(self.playlist.uid).get(md5)
        return entry.records if entry else ""

    def run(self, order: str = "list_loop") -> int:
        deps = Deps(
            library=self.library,
            stats=self.stats,
            player=self.player,
            screen=self.screen,
            keys=self.keys,
            clock=self.clock,
            rng=self.rng,
        )
        session = Session(deps, self.playlist, self.params, order, self.songs)
        return session.run()


@pytest.fixture
def simple_env(tmp_path) -> SimpleEnv:
    return SimpleEnv(tmp_path)
