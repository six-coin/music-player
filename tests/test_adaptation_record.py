"""自适应：阈值边界、短歌、自动跳过不记录。"""

from __future__ import annotations

import random

from app.core.adaptation import Params
from app.core.stats import SongStats


def test_skip_below_threshold_records_one(simple_env):
    first = simple_env.add("a")
    simple_env.add("b")
    simple_env.player.polls = 20
    simple_env.clock.step = 1.0
    simple_env.keys.skip_at = 10  # 约 10 秒，阈值 30 秒
    simple_env.keys.quit_at = 12
    simple_env.run()
    assert simple_env.records(first) == "1"


def test_skip_exactly_at_threshold_records_zero(simple_env):
    first = simple_env.add("a")
    simple_env.add("b")
    simple_env.player.polls = 20
    simple_env.params = Params(window=100, min_plays=10, base=0.95, skip_seconds=5)
    simple_env.clock.step = 1.0
    simple_env.keys.skip_at = 5  # 正好 5 秒：不算「阈值内」
    simple_env.keys.quit_at = 7
    simple_env.run()
    assert simple_env.records(first) == "0"


def test_skip_after_threshold_records_zero(simple_env):
    first = simple_env.add("a")
    simple_env.add("b")
    simple_env.player.polls = 20
    simple_env.params = Params(window=100, min_plays=10, base=0.95, skip_seconds=5)
    simple_env.clock.step = 1.0
    simple_env.keys.skip_at = 10
    simple_env.keys.quit_at = 12
    simple_env.run()
    assert simple_env.records(first) == "0"


def test_short_song_finished_naturally_records_zero(simple_env):
    first = simple_env.add("a")
    simple_env.add("b")
    simple_env.keys.quit_at = 9  # 第 1 首约 1 秒就播完了
    simple_env.run()
    assert simple_env.records(first) == "0"


def test_auto_skip_counts_but_records_nothing(simple_env):
    first = simple_env.add("a")
    second = simple_env.add("b")
    simple_env.playlist.adaptation.enabled = True
    # 2 条记录、全部跳过、min_plays=1 → 概率 0.99，这一轮必跳过
    simple_env.params = Params(window=100, min_plays=1, base=0.99, skip_seconds=30)
    simple_env.stats.save(simple_env.playlist.uid, {first: SongStats(records="11")})
    simple_env.rng = random.Random(1)  # 第一个随机数约 0.13，小于 0.99
    simple_env.player.polls = 20
    simple_env.keys.quit_at = 3
    simple_env.run()

    entry = simple_env.stats.load(simple_env.playlist.uid)[first]
    assert entry.records == "11"  # 判定不写记录
    assert entry.auto_skipped == 1
    assert simple_env.player.played[0].name == f"{second}.mp3"
    assert [state.title for state in simple_env.screen.states] == ["Song b"]


def test_adaptation_disabled_never_skips(simple_env):
    first = simple_env.add("a")
    simple_env.add("b")
    simple_env.playlist.adaptation.enabled = False
    simple_env.params = Params(window=100, min_plays=1, base=0.99, skip_seconds=30)
    simple_env.stats.save(simple_env.playlist.uid, {first: SongStats(records="1" * 100)})
    simple_env.rng = random.Random(1)  # 开着的话这一轮必跳过
    simple_env.player.polls = 20
    simple_env.keys.quit_at = 3
    simple_env.run()
    assert simple_env.player.played[0].name == f"{first}.mp3"


def test_window_caps_the_records(simple_env):
    first = simple_env.add("a")
    simple_env.add("b")
    simple_env.params = Params(window=3, min_plays=0, base=0.95, skip_seconds=30)
    simple_env.stats.save(simple_env.playlist.uid, {first: SongStats(records="000")})
    simple_env.keys.quit_at = 9
    simple_env.run()
    assert len(simple_env.records(first)) == 3
