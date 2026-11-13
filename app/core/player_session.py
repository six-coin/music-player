"""player 的队列与模式状态机。

只做一件事：给定歌单、模式与当前曲，回答「下一首是谁」。不读文件、不写统计、
不碰界面——文件在不在、要不要跳过，都由注入的 ``Hooks`` 决定。
每次换曲产出一条 ``Load`` / ``Stop`` 命令，界面按 ``seq`` 去重执行。
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from app.core.library import Library
from app.core.playlists import PlaylistStore
from app.core.queue import build_round, play_order
from app.errors import PlaylistCycleError

MODES = ("shuffle", "list_loop", "repeat_one")

MISSING = "missing"
FAILED = "failed"
CYCLE = "cycle"
ALL_SKIPPED = "all_skipped"


@dataclass(frozen=True, slots=True)
class Load:
    seq: int
    md5: str
    position_ms: int
    autoplay: bool


@dataclass(frozen=True, slots=True)
class Stop:
    seq: int


@dataclass(frozen=True, slots=True)
class Pin:
    """单曲循环选了一首不在当前歌单里的歌。"""

    md5: str
    origin_index: int
    origin_position_ms: int
    playlist_uid: str | None


@dataclass(frozen=True, slots=True)
class Notice:
    seq: int
    kind: str
    md5: str = ""
    count: int = 0


@dataclass(slots=True)
class Hooks:
    """状态机伸手要的三件外部事实；默认实现让纯测试可以什么都不传。"""

    available: Callable[[str], bool] = lambda _md5: True
    should_skip: Callable[[str, str], bool] = lambda _uid, _md5: False
    on_auto_skip: Callable[[str, str], None] = lambda _uid, _md5: None


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


class PlayerSession:
    def __init__(
        self,
        library: Library,
        playlists: PlaylistStore,
        mode: str = "shuffle",
        rng: random.Random | None = None,
        hooks: Hooks | None = None,
    ) -> None:
        self._library = library
        self._playlists = playlists
        self._rng = rng or random.Random()
        self._hooks = hooks or Hooks()

        self.mode = mode if mode in MODES else "shuffle"
        self.playlist_uid: str | None = None
        self.current_md5: str | None = None
        self.playing = False
        self.position_ms = 0
        self.pin: Pin | None = None
        self.empty: str | None = "no_selection"

        self._songs: list[str] = []
        self.order: list[str] = []
        self.index = -1

        self._seq = 0
        self._notice_seq = 0
        self.notice: Notice | None = None
        self._command: Load | Stop | None = None

    # ---------- 读 ----------

    @property
    def command(self) -> Load | Stop | None:
        return self._command

    def snapshot(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "playlist_uid": self.playlist_uid,
            "current_md5": self.current_md5,
            "position_ms": self.position_ms,
            "playing": self.playing,
            "can_prev": self.can_prev(),
            "can_next": self.can_next(),
            "queue": [{"md5": md5, "state": state} for md5, state in self.queue()],
            "pinned": self.pin.md5 if self.pin is not None else None,
            "empty": self.empty,
            "notice": self.notice,
            "command": self._command,
        }

    def queue(self) -> list[tuple[str, str]]:
        """整张歌单，以及每首的位置：``played`` / ``current`` / ``upcoming``。

        队列永远显示完整歌单，不做截断；单曲循环没有「已播」，除当前曲外都是待播。
        """
        if self.pin is not None:
            return []
        if self.mode == "repeat_one":
            return [
                (md5, "current" if position == self.index else "upcoming")
                for position, md5 in enumerate(self.order)
            ]
        result: list[tuple[str, str]] = []
        for position, md5 in enumerate(self.order):
            if position < self.index:
                result.append((md5, "played"))
            elif position == self.index:
                result.append((md5, "current"))
            else:
                result.append((md5, "upcoming"))
        return result

    def can_prev(self) -> bool:
        if self.pin is not None:
            return self.pin.origin_index > 0
        return any(
            self._verdict(self.order[position], judge=False) == "take"
            for position in range(self.index - 1, -1, -1)
        )

    def can_next(self) -> bool:
        return bool(self._songs)

    # ---------- 装载 ----------

    def load_playlist(self, uid: str, *, autoplay: bool) -> bool:
        playlist = self._playlists.get(uid)
        if playlist is None:
            return False
        try:
            content = self._playlists.resolve(uid, self._library)
        except PlaylistCycleError:
            self.note(CYCLE)
            return False

        self.playlist_uid = uid
        self.pin = None
        self._songs = _unique(play_order(content, self._library))
        self.position_ms = 0

        if not self._songs:
            self.order = []
            self.index = -1
            self.current_md5 = None
            self.empty = "empty_playlist"
            self._emit_stop()
            return True

        self.empty = None
        self.order = build_round(self._songs, self.mode, self._rng)
        self.index = 0
        self.current_md5 = self.order[0]
        self._emit(self.current_md5, 0, autoplay)

        verdict = self._verdict(self.current_md5, judge=False)
        if verdict == "missing":
            self.note(MISSING, self.current_md5, 1)
        if verdict != "take":
            self._advance(judge=False, autoplay=autoplay)
        return True

    def restore(self, playlist_uid: str | None, md5: str | None, position_ms: int) -> None:
        """按上次记住的歌单、曲目、位置落位；永远不自动播。"""
        playlist = self._playlists.get(playlist_uid) if playlist_uid else None
        if playlist is None:
            self.playlist_uid = None
            self.empty = "no_selection"
            return

        try:
            content = self._playlists.resolve(playlist.uid, self._library)
        except PlaylistCycleError:
            self.playlist_uid = None
            self.empty = "no_selection"
            self.note(CYCLE)
            return

        self.playlist_uid = playlist.uid
        self._songs = _unique(play_order(content, self._library))
        self.pin = None

        if not self._songs:
            self.order = []
            self.index = -1
            self.current_md5 = None
            self.empty = "empty_playlist"
            self._emit_stop()
            return

        self.empty = None
        target = md5 if md5 in self._songs else self._songs[0]
        position = max(0, position_ms) if target == md5 else 0
        self._rebuild_around(target)
        self.current_md5 = target
        self.position_ms = position
        self._emit(target, position, False)

        verdict = self._verdict(target, judge=False)
        if verdict == "missing":
            self.note(MISSING, target, 1)
        if verdict != "take":
            self._advance(judge=False, autoplay=False)

    # ---------- 切歌 ----------

    def next(self) -> bool:
        if self.pin is not None:
            self.index = max(0, min(self.pin.origin_index, len(self.order) - 1))
            self.pin = None
        return self._advance(judge=True, autoplay=True)

    def previous(self) -> bool:
        if self.pin is not None:
            self.index = max(0, min(self.pin.origin_index, len(self.order) - 1))
            self.pin = None
        for position in range(self.index - 1, -1, -1):
            if self._verdict(self.order[position], judge=False) == "take":
                self.index = position
                self.current_md5 = self.order[position]
                self._emit(self.current_md5, 0, True)
                return True
        return False

    def jump(self, md5: str) -> bool:
        if md5 == self.current_md5:
            return False
        if md5 not in self.order:
            return False
        self.index = self.order.index(md5)
        self.pin = None
        self.current_md5 = md5
        self.empty = None
        self._emit(md5, 0, True)
        return True

    def on_ended(self) -> bool:
        if self.mode == "repeat_one" and self.current_md5:
            self._emit(self.current_md5, 0, True)
            return True
        return self._advance(judge=True, autoplay=True)

    def on_failed(self, md5: str) -> bool:
        if md5 != self.current_md5:
            return False
        return self._advance(judge=True, autoplay=True)

    # ---------- 模式与单曲循环 ----------

    def set_mode(self, mode: str) -> bool:
        if mode not in MODES or mode == self.mode:
            return False
        previous = self.mode
        self.mode = mode

        if previous == "repeat_one" and self.pin is not None:
            pin = self.pin
            self.pin = None
            if not self.order:
                self.current_md5 = None
                self.empty = "no_selection"
                self._emit_stop()
                return True
            self.index = max(0, min(pin.origin_index, len(self.order) - 1))
            self.current_md5 = self.order[self.index]
            self.empty = None
            self._emit(self.current_md5, pin.origin_position_ms, self.playing)
            return True

        if self.current_md5 is not None:
            self._rebuild_around(self.current_md5)
        return True

    def pick_loop_song(self, md5: str) -> bool:
        if self._library.find_music(md5) is None:
            return False
        self.mode = "repeat_one"
        self.empty = None
        if md5 == self.current_md5:
            return True
        if md5 in self.order:
            self.jump(md5)
            self.pin = None
            return True
        self.pin = Pin(md5, self.index, self.position_ms, self.playlist_uid)
        self.current_md5 = md5
        self._emit(md5, 0, True)
        return True

    # ---------- 播放状态（镜像，由网页上报） ----------

    def set_playing(self, on: bool) -> None:
        self.playing = bool(on)

    def set_position(self, position_ms: int) -> None:
        self.position_ms = max(0, int(position_ms))

    def note(self, kind: str, md5: str = "", count: int = 0) -> None:
        self._notice_seq += 1
        self.notice = Notice(self._notice_seq, kind, md5, count)

    # ---------- 内部 ----------

    def _advance(self, *, judge: bool, autoplay: bool) -> bool:
        missing: list[str] = []
        picked = self._scan(self.index + 1, len(self.order), judge, missing)
        if picked is None:
            if not self._next_round():
                self._stop(all_skipped=judge and not missing)
                if missing:
                    self.note(MISSING, missing[0], len(missing))
                return False
            picked = self._scan(0, len(self.order), judge, missing)
        if picked is None:
            self._stop(all_skipped=judge and not missing)
            if missing:
                self.note(MISSING, missing[0], len(missing))
            return False

        self.index, self.current_md5 = picked
        self.empty = None
        self._emit(self.current_md5, 0, autoplay)
        if missing:
            self.note(MISSING, missing[0], len(missing))
        return True

    def _scan(
        self, start: int, end: int, judge: bool, missing: list[str]
    ) -> tuple[int, str] | None:
        for position in range(max(0, start), end):
            md5 = self.order[position]
            verdict = self._verdict(md5, judge=judge)
            if verdict == "take":
                return position, md5
            if verdict == "missing":
                missing.append(md5)
        return None

    def _verdict(self, md5: str, *, judge: bool) -> str:
        if not self._hooks.available(md5):
            return "missing"
        if judge and self.playlist_uid and self._hooks.should_skip(self.playlist_uid, md5):
            self._hooks.on_auto_skip(self.playlist_uid, md5)
            return "skip"
        return "take"

    def _next_round(self) -> bool:
        """一轮播完才生成下一轮；生成之后不保留上一轮的历史。"""
        if not self._songs:
            return False
        previous_last = self.order[-1] if self.order else None
        self.order = build_round(self._songs, self.mode, self._rng, previous_last)
        self.index = -1
        return True

    def _rebuild_around(self, md5: str) -> None:
        if self.mode == "shuffle" and md5 in self._songs:
            rest = [item for item in self._songs if item != md5]
            self._rng.shuffle(rest)
            self.order = [md5, *rest]
            self.index = 0
        else:
            self.order = list(self._songs)
            self.index = self.order.index(md5) if md5 in self.order else 0

    def _stop(self, *, all_skipped: bool) -> None:
        self.current_md5 = None
        self.position_ms = 0
        self.index = len(self.order)
        self.empty = "unplayable"
        self._emit_stop()
        if all_skipped:
            self.note(ALL_SKIPPED)

    def _emit(self, md5: str, position_ms: int, autoplay: bool) -> None:
        self._seq += 1
        self._command = Load(self._seq, md5, max(0, int(position_ms)), bool(autoplay))
        self.playing = bool(autoplay)
        self.position_ms = max(0, int(position_ms))

    def _emit_stop(self) -> None:
        self._seq += 1
        self._command = Stop(self._seq)
        self.playing = False
