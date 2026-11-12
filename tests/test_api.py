"""管理器接口层：快照结构与非法参数。"""

from __future__ import annotations

from app.ui.manager.api import ManagerApi


def test_snapshot_has_expected_shape(tmp_path, music_factory):
    api = ManagerApi(config_dir=tmp_path)
    api.library.upsert_music(music_factory("a"))

    state = api.get_state()

    assert state["ok"] is True
    assert state["section"] == "overview"
    assert state["counts"]["musics"] == 1
    assert state["counts"]["playlists"] == 1
    assert state["playlists"][0]["builtin"] is True
    assert state["library"]["musics"][0]["title"] == "Song a"


def test_invalid_section_is_ignored(tmp_path):
    api = ManagerApi(config_dir=tmp_path)
    api.select_section("songs")

    state = api.select_section("nope")

    assert state["section"] == "songs"


def test_overview_lists_recent_imports(tmp_path, music_factory):
    api = ManagerApi(config_dir=tmp_path)
    api.library.upsert_music(music_factory("a", created_at=100, updated_at=100))

    overview = api.get_state()["overview"]

    assert overview["recent_imported"][0]["md5"] == "a" * 32
    assert "Song a" in [item["title"] for item in overview["recent_edited"]]


def test_counts_include_total_duration(tmp_path, music_factory):
    api = ManagerApi(config_dir=tmp_path)
    api.library.upsert_music(music_factory("a", duration_ms=1000, size=10))
    api.library.upsert_music(music_factory("b", duration_ms=2000, size=20))

    counts = api.get_state()["counts"]

    assert counts["total_duration_ms"] == 3000
    assert counts["total_size"] == 30


def test_empty_library_reports_no_issues(tmp_path):
    api = ManagerApi(config_dir=tmp_path)

    overview = api.get_state()["overview"]

    assert overview["issues"] == []
    assert overview["recent_imported"] == []
