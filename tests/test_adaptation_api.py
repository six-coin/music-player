"""自适应的参数、统计与设置项。"""

from __future__ import annotations

import pytest

from app.core.stats import SongStats
from app.ui.manager.api import ManagerApi


def make_api(tmp_path) -> ManagerApi:
    return ManagerApi(config_dir=tmp_path)


def test_probability_matches_formula(tmp_path, music_factory):
    api = make_api(tmp_path)
    api.library.upsert_music(music_factory("a"))
    api.library.save()
    playlist = api.playlists.default()
    # 100 条记录里跳过 50 次：0.95 × 50/100 = 0.475
    api.stats.save(playlist.uid, {"a" * 32: SongStats(records="1" * 50 + "0" * 50)})

    data = api.get_playlist_stats(playlist.uid)

    assert data["ok"] is True
    row = data["rows"][0]
    assert row["total"] == 100
    assert row["skips"] == 50
    assert row["rate"] == pytest.approx(0.5)
    assert row["probability"] == pytest.approx(0.475)


def test_min_plays_keeps_probability_at_zero(tmp_path, music_factory):
    api = make_api(tmp_path)
    api.library.upsert_music(music_factory("a"))
    api.library.save()
    playlist = api.playlists.default()
    api.stats.save(playlist.uid, {"a" * 32: SongStats(records="1" * 10)})

    row = api.get_playlist_stats(playlist.uid)["rows"][0]

    assert row["total"] == 10
    assert row["probability"] == 0.0


def test_update_adaptation_sets_and_clears_overrides(tmp_path):
    api = make_api(tmp_path)
    playlist = api.playlists.default()

    api.update_adaptation(playlist.uid, {"enabled": True, "window": 50, "base": 0.8})

    adapt = api.playlists.get(playlist.uid).adaptation
    assert adapt.enabled is True
    assert adapt.window == 50
    assert adapt.base == pytest.approx(0.8)

    api.update_adaptation(playlist.uid, {"window": None})

    assert api.playlists.get(playlist.uid).adaptation.window is None


def test_update_adaptation_clamps_values(tmp_path):
    api = make_api(tmp_path)
    playlist = api.playlists.default()

    api.update_adaptation(
        playlist.uid, {"window": 99999, "min_plays": 99999, "base": 5, "skip_seconds": 1}
    )

    adapt = api.playlists.get(playlist.uid).adaptation
    assert adapt.window == 1000
    assert adapt.min_plays == 1000
    assert adapt.base == pytest.approx(0.99)
    assert adapt.skip_seconds == 5


def test_reset_stats_single_and_all(tmp_path, music_factory):
    api = make_api(tmp_path)
    api.library.upsert_music(music_factory("a"))
    api.library.upsert_music(music_factory("b"))
    api.library.save()
    playlist = api.playlists.default()
    api.stats.save(
        playlist.uid,
        {"a" * 32: SongStats(records="10"), "b" * 32: SongStats(records="01")},
    )

    api.reset_stats(playlist.uid, "a" * 32)
    assert "a" * 32 not in api.stats.load(playlist.uid)
    assert "b" * 32 in api.stats.load(playlist.uid)

    api.reset_stats(playlist.uid, "")
    assert api.stats.load(playlist.uid) == {}


def test_music_stats_aggregates_playlists(tmp_path, music_factory):
    api = make_api(tmp_path)
    api.library.upsert_music(music_factory("a"))
    api.library.save()
    first = api.playlists.default()
    second = api.playlists.create("另一个", "manual")
    second.entries = ["a" * 32]
    api.stats.save(first.uid, {"a" * 32: SongStats(records="11", auto_skipped=2)})
    api.stats.save(second.uid, {"a" * 32: SongStats(records="0")})

    data = api.get_music_stats("a" * 32)

    assert data["ok"] is True
    assert len(data["playlists"]) == 2
    assert data["total"] == 3
    assert data["skips"] == 2
    assert data["rate"] == pytest.approx(2 / 3)


def test_music_stats_for_unknown_song(tmp_path):
    api = make_api(tmp_path)

    assert api.get_music_stats("f" * 32)["ok"] is False


def test_update_settings_clamps_volume(tmp_path):
    api = make_api(tmp_path)

    api.update_settings({"player": {"volume": 2.5}})
    assert api.settings.get("player", "volume") == 1.0

    api.update_settings({"player": {"volume": 0.3}})
    assert api.settings.get("player", "volume") == pytest.approx(0.3)


def test_set_theme_and_snapshot(tmp_path):
    api = make_api(tmp_path)

    state = api.set_theme("dark")

    assert api.settings.get("common", "theme") == "dark"
    assert state["theme"] == "dark"

    api.set_theme("紫色的")
    assert api.settings.get("common", "theme") == "dark"


def test_clear_all_stats(tmp_path, music_factory):
    api = make_api(tmp_path)
    api.library.upsert_music(music_factory("a"))
    api.library.save()
    playlist = api.playlists.default()
    api.stats.save(playlist.uid, {"a" * 32: SongStats(records="1")})

    api.clear_all_stats()

    assert not api.stats.path_for(playlist.uid).exists()


def test_snapshot_carries_status(tmp_path):
    api = make_api(tmp_path)

    status = api.get_state()["status"]

    assert "ffmpeg" in status
    assert status["data_dir"] == str(tmp_path)
    assert status["program_dir"]
