"""播放循环：播完 / 跳过 / 退出三条路径。

轮询次数是算出来的：``FakePlayer`` 默认播 3 次轮询后判定播完，``FakeClock``
每读一次表前进 0.1 秒，所以第 1 首在第 7 次轮询结束（3 次出声 + 4 次 0.4 秒宽限）。
"""

from __future__ import annotations

from app import paths


def test_natural_finish_records_not_skipped(simple_env):
    first = simple_env.add("a")
    second = simple_env.add("b")
    simple_env.keys.quit_at = 9  # 第 1 首已播完，第 2 首刚开始
    assert simple_env.run() == 0
    assert simple_env.player.played[0].name == f"{first}.mp3"
    assert simple_env.records(first) == "0"
    assert simple_env.records(second) == ""


def test_skip_stops_the_song_and_moves_on(simple_env):
    first = simple_env.add("a")
    second = simple_env.add("b")
    simple_env.player.polls = 20  # 不让它自然播完
    simple_env.keys.skip_at = 2
    simple_env.keys.quit_at = 6
    assert simple_env.run() == 0
    assert simple_env.records(first) == "1"
    assert simple_env.player.played[1].name == f"{second}.mp3"
    assert simple_env.player.stops == 2  # 跳过一次、退出一次
    assert [state.index for state in simple_env.screen.states] == [1, 2]


def test_quit_records_nothing(simple_env):
    first = simple_env.add("a")
    simple_env.add("b")
    simple_env.player.polls = 20
    simple_env.keys.quit_at = 1
    assert simple_env.run() == 0
    assert simple_env.records(first) == ""
    assert simple_env.player.stops == 1


def test_missing_file_is_skipped_without_record(simple_env):
    first = simple_env.add("a")
    second = simple_env.add("b")
    paths.music_path(first, "mp3").unlink()
    simple_env.player.polls = 20
    simple_env.keys.quit_at = 3
    assert simple_env.run() == 0
    assert simple_env.records(first) == ""
    assert [path.name for path in simple_env.player.played] == [f"{second}.mp3"]


def test_play_failure_is_not_recorded(simple_env):
    first = simple_env.add("a")
    second = simple_env.add("b")
    simple_env.player.fail_first = True
    simple_env.player.polls = 20
    simple_env.keys.quit_at = 3
    assert simple_env.run() == 0
    assert simple_env.records(first) == ""
    assert simple_env.player.played[1].name == f"{second}.mp3"


def test_state_carries_playlist_and_mode(simple_env):
    simple_env.add("a")
    simple_env.add("b")
    simple_env.player.polls = 20
    simple_env.keys.quit_at = 2
    simple_env.run("shuffle")
    state = simple_env.screen.states[0]
    assert state.playlist == "默认歌单"
    assert state.order == "shuffle"
    assert state.total == 2
