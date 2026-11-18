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


def test_preview_language_does_not_write_settings(tmp_path):
    """首次运行的语言下拉框只换内存：写了设置就等于跳过了首次运行。"""
    from app import i18n

    api = ManagerApi(config_dir=tmp_path)
    settings_file = tmp_path / "settings.json"
    before = settings_file.read_bytes()

    result = api.preview_language("en-US")

    assert result["language"] == "en-US"
    assert i18n.current() == "en-US"
    assert settings_file.read_bytes() == before


def test_preview_language_ignores_an_unknown_code(tmp_path):
    api = ManagerApi(config_dir=tmp_path)
    api.preview_language("en-US")

    result = api.preview_language("xx-XX")

    assert result["language"] == "en-US"


# ---------- 快捷键 ----------


def test_snapshot_lists_shortcut_actions(tmp_path):
    api = ManagerApi(config_dir=tmp_path)

    keys = api.get_state()["keys"]

    assert keys["actions"]["player"][0] == "play_pause"
    assert keys["defaults"]["simple"]["quit"] == "Ctrl+Q"


def test_set_shortcut_normalizes_and_persists(tmp_path):
    api = ManagerApi(config_dir=tmp_path)

    state = api.set_shortcut("player", "next", "ctrl+n")

    assert state["ok"] is True
    assert state["shortcut"] == {"group": "player", "action": "next", "spec": "Ctrl+N"}
    assert state["settings"]["player"]["keys"]["next"] == "Ctrl+N"


def test_set_shortcut_rejects_a_duplicate(tmp_path):
    api = ManagerApi(config_dir=tmp_path)

    result = api.set_shortcut("player", "prev", "Ctrl+C")

    assert result == {"ok": False, "reason": "conflict", "action": "next"}


def test_set_shortcut_rejects_what_the_console_cannot_read(tmp_path):
    api = ManagerApi(config_dir=tmp_path)

    assert api.set_shortcut("simple", "skip", "Alt+S")["reason"] == "unsupported"


def test_set_shortcut_rejects_a_modifier_only_combo(tmp_path):
    api = ManagerApi(config_dir=tmp_path)

    assert api.set_shortcut("player", "next", "Ctrl")["reason"] == "invalid"


def test_set_shortcut_ignores_unknown_actions(tmp_path):
    api = ManagerApi(config_dir=tmp_path)

    assert api.set_shortcut("player", "nope", "Ctrl+J")["ok"] is False
    assert api.set_shortcut("nope", "next", "Ctrl+J")["ok"] is False
