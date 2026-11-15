"""歌曲级总播放次数：只受自己的总开关控制，与自适应互不影响。"""

from __future__ import annotations

import json

from app.core.adaptation import is_full_play
from app.core.totals import TotalStore
from app.ui.manager.api import ManagerApi

SONG = "a" * 32
OTHER = "b" * 32


# ---------- 存储 ----------


def test_add_persists_and_accumulates(tmp_path):
    store = TotalStore(tmp_path / "totals.json")

    assert store.add(SONG) == 1
    assert store.add(SONG) == 2

    assert store.get(SONG) == 2
    saved = json.loads((tmp_path / "totals.json").read_text(encoding="utf-8"))
    assert saved["version"] == 1
    assert saved["songs"] == {SONG: 2}


def test_missing_file_reads_as_empty(tmp_path):
    assert TotalStore(tmp_path / "totals.json").summary() == {}


def test_broken_file_is_treated_as_empty(tmp_path):
    path = tmp_path / "totals.json"
    path.write_text("{ not json", encoding="utf-8")
    store = TotalStore(path)

    assert store.load_safe() == {}
    # 坏文件不该让计数停摆：下一次写入直接覆盖它。
    assert store.add(SONG) == 1
    assert store.get(SONG) == 1


def test_bad_values_are_clamped_or_dropped(tmp_path):
    path = tmp_path / "totals.json"
    path.write_text(
        json.dumps({"version": 1, "songs": {SONG: -3, OTHER: "7", "c" * 32: 2}}),
        encoding="utf-8",
    )

    assert TotalStore(path).load() == {SONG: 0, "c" * 32: 2}


def test_drop_removes_one_song(tmp_path):
    store = TotalStore(tmp_path / "totals.json")
    store.add(SONG, 3)
    store.add(OTHER, 1)

    assert store.drop(SONG) is True
    assert store.drop(SONG) is False
    assert store.summary() == {OTHER: 1}


def test_move_key_merges_on_replace(tmp_path):
    store = TotalStore(tmp_path / "totals.json")
    store.add(SONG, 3)
    store.add(OTHER, 2)

    assert store.move_key(OTHER, SONG) is True

    assert store.summary() == {SONG: 5}
    assert store.move_key("d" * 32, SONG) is False


# ---------- 判定 ----------


def test_is_full_play_boundary():
    assert is_full_play(0, 30, natural=True) is True
    assert is_full_play(29_999, 30, natural=False) is False
    assert is_full_play(30_000, 30, natural=False) is True
    assert is_full_play(10, 0, natural=False) is True


# ---------- 与自适应互不影响 ----------


def test_song_stats_expose_total_plays(tmp_path, music_factory):
    api = ManagerApi(config_dir=tmp_path)
    api.library.upsert_music(music_factory("a"))
    api.library.save()
    api.totals.add(SONG, 4)

    assert api.get_music_stats(SONG)["total_plays"] == 4
    rows = api.get_playlist_stats(api.playlists.default().uid)["rows"]
    assert [row["total_plays"] for row in rows] == [4]


def test_total_plays_survive_clearing_adaptation(tmp_path, music_factory):
    api = ManagerApi(config_dir=tmp_path)
    api.library.upsert_music(music_factory("a"))
    api.library.save()
    uid = api.playlists.default().uid
    api.stats.record(uid, SONG, skipped=False, window=100)
    api.totals.add(SONG, 3)

    api.reset_stats(uid, SONG)
    assert api.stats.load(uid) == {}
    assert api.totals.get(SONG) == 3

    api.clear_all_stats()
    assert api.totals.get(SONG) == 3


def test_deleting_a_song_drops_its_total_plays(tmp_path, music_factory):
    api = ManagerApi(config_dir=tmp_path)
    api.library.upsert_music(music_factory("a"))
    api.library.save()
    api.totals.add(SONG, 2)

    api.delete_musics([SONG])

    assert api.totals.get(SONG) == 0


# ---------- simple ----------


def test_simple_counts_a_natural_end(simple_env):
    first = simple_env.add("a")
    simple_env.add("b")
    simple_env.keys.quit_at = 9

    simple_env.run()

    assert simple_env.records(first) == "0"
    assert simple_env.total_plays(first) == 1


def test_simple_ignores_short_skips(simple_env):
    first = simple_env.add("a")
    simple_env.add("b")
    simple_env.player.polls = 20
    simple_env.clock.step = 1.0
    simple_env.keys.skip_at = 10  # 10 秒 < 阈值 30 秒
    simple_env.keys.quit_at = 12

    simple_env.run()

    assert simple_env.records(first) == "1"
    assert simple_env.total_plays(first) == 0


def test_simple_counts_even_when_adaptation_is_off(simple_env):
    first = simple_env.add("a")
    simple_env.add("b")
    simple_env.playlist.adaptation.enabled = False
    simple_env.keys.quit_at = 9

    simple_env.run()

    assert simple_env.stats.load(simple_env.playlist.uid) == {}
    assert simple_env.total_plays(first) == 1
