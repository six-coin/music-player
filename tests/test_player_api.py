"""JS 桥：快照结构、非法参数、不写库、令牌一致。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app import paths
from app.settings import defaults
from app.ui.player.api import PlayerApi

UID = "d" * 32


def md5(char: str) -> str:
    return char * 32


def merge(base: dict, patch: dict) -> dict:
    result = json.loads(json.dumps(base))
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = value
    return result


def write_config(
    tmp_path: Path,
    entries: tuple[str, ...] = ("a", "b", "c"),
    extra: tuple[str, ...] = (),
    adaptation: bool = True,
    patch: dict | None = None,
) -> None:
    chars = [*entries, *extra]
    musics = [
        {
            "md5": md5(char),
            "names": [f"Song {char}"],
            "authors": [],
            "tags": [],
            "ext": "mp3",
            "duration_ms": 1000,
        }
        for char in chars
    ]
    library = {"version": 1, "authors": [], "tag_groups": [], "musics": musics}
    playlists = {
        "version": 1,
        "default_uid": UID,
        "items": [
            {
                "uid": UID,
                "name": None,
                "builtin": True,
                "kind": "manual",
                "entries": [md5(char) for char in entries],
                "filters": [],
                "adaptation": {"enabled": adaptation},
            }
        ],
    }
    settings = defaults()
    settings["player"]["order"] = "list_loop"
    if patch:
        settings = merge(settings, patch)

    (tmp_path / "library.json").write_text(
        json.dumps(library, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "playlists.json").write_text(
        json.dumps(playlists, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "settings.json").write_text(
        json.dumps(settings, ensure_ascii=False), encoding="utf-8"
    )
    for char in chars:
        path = paths.music_path(md5(char), "mp3")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake")


@pytest.fixture
def api(tmp_path):
    write_config(tmp_path)
    player = PlayerApi(config_dir=tmp_path)
    yield player
    player.close()


def test_snapshot_shape(api):
    data = api.get_state()

    assert data["ok"] is True
    assert data["language"] == "zh-CN"
    assert data["playlists"] == [{"uid": UID, "title": "默认歌单", "count": 3, "active": False}]
    assert data["track"] is None
    assert data["empty"] == "no_selection"
    assert data["command"] is None
    assert data["transport"] == {"playing": False, "can_prev": False, "can_next": False}


def test_select_playlist_starts_playing(api):
    data = api.select_playlist(UID)

    assert data["track"]["md5"] == md5("a")
    assert data["track"]["missing"] is False
    assert data["transport"]["playing"] is True
    assert data["command"]["kind"] == "load"
    assert data["command"]["autoplay"] is True
    assert data["command"]["url"].startswith("http://127.0.0.1:")
    assert data["empty"] is None


def test_selecting_the_same_playlist_is_a_noop(api):
    first = api.select_playlist(UID)
    seq = first["command"]["seq"]

    second = api.select_playlist(UID)

    assert second["track"]["md5"] == first["track"]["md5"]
    assert second["command"]["seq"] == seq


def test_queue_snapshot_has_three_states(api):
    data = api.select_playlist(UID)

    assert [(item["md5"], item["state"]) for item in data["queue"]["items"]] == [
        (md5("a"), "current"),
        (md5("b"), "upcoming"),
        (md5("c"), "upcoming"),
    ]
    assert "more" not in data["queue"]

    data = api.next_track(md5("a"), 1000)
    assert [item["state"] for item in data["queue"]["items"]] == [
        "played",
        "current",
        "upcoming",
    ]


def test_previous_does_not_record(api, tmp_path):
    api.select_playlist(UID)
    api.next_track(md5("a"), 1000)  # 只有这一步记账
    api.prev_track(md5("b"), 1000)

    stats = json.loads((tmp_path / "stats" / f"{UID}.json").read_text(encoding="utf-8"))
    assert set(stats["songs"]) == {md5("a")}


def test_jump_does_not_record(api, tmp_path):
    api.select_playlist(UID)
    api.jump_to(md5("c"), 1000)

    assert not (tmp_path / "stats" / f"{UID}.json").exists()


def test_player_leaves_library_untouched(api, tmp_path):
    before = (
        (tmp_path / "library.json").read_bytes(),
        (tmp_path / "playlists.json").read_bytes(),
    )

    api.select_playlist(UID)
    api.next_track(md5("a"), 1000)
    api.set_mode("repeat_one")
    api.jump_to(md5("c"), 2000)
    api.track_ended(md5("c"), 1000)
    api.set_volume(0.4)
    api.close()

    after = (
        (tmp_path / "library.json").read_bytes(),
        (tmp_path / "playlists.json").read_bytes(),
    )
    assert before == after


def test_invalid_arguments_do_not_raise(api):
    assert api.select_playlist(123)["ok"] is True
    assert api.set_mode("nope")["ok"] is True
    assert api.jump_to(None)["ok"] is True
    assert api.report_position("x") == {"ok": True}
    assert api.set_volume("x") == {"ok": False}
    assert api.track_ended(None, None)["ok"] is True


def test_volume_is_clamped_and_persisted(api, tmp_path):
    api.set_volume(2)
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["player"]["volume"] == 1.0

    api.set_volume(-3)
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["player"]["volume"] == 0.0


def test_patch_player_keeps_other_sections(api, tmp_path):
    path = tmp_path / "settings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["common"]["theme"] = "dark"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    api.set_volume(0.5)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["common"]["theme"] == "dark"
    assert saved["player"]["volume"] == 0.5


def test_track_ended_records_a_zero(api, tmp_path):
    api.select_playlist(UID)
    api.track_ended(md5("a"), 900)

    stats = json.loads((tmp_path / "stats" / f"{UID}.json").read_text(encoding="utf-8"))
    assert stats["songs"][md5("a")]["records"] == "0"


def test_track_ended_advances(api):
    api.select_playlist(UID)
    data = api.track_ended(md5("a"), 900)

    assert data["track"]["md5"] == md5("b")


def test_stale_ended_event_is_ignored(api):
    api.select_playlist(UID)
    data = api.track_ended(md5("f"), 900)

    assert data["track"]["md5"] == md5("a")


def test_manual_skip_records_a_one(api, tmp_path):
    api.select_playlist(UID)
    api.next_track(md5("a"), 1000)

    stats = json.loads((tmp_path / "stats" / f"{UID}.json").read_text(encoding="utf-8"))
    assert stats["songs"][md5("a")]["records"] == "1"


def test_no_stats_when_adaptation_is_off(tmp_path):
    write_config(tmp_path, adaptation=False)
    player = PlayerApi(config_dir=tmp_path)
    try:
        player.select_playlist(UID)
        player.next_track(md5("a"), 1000)
        assert not (tmp_path / "stats" / f"{UID}.json").exists()
    finally:
        player.close()


def test_queue_visible_persists(tmp_path):
    write_config(tmp_path)
    first = PlayerApi(config_dir=tmp_path)
    try:
        first.set_queue_visible(False)
    finally:
        first.close()

    second = PlayerApi(config_dir=tmp_path)
    try:
        assert second.get_state()["queue"]["visible"] is False
    finally:
        second.close()


def test_remember_progress_false_writes_zero(tmp_path):
    write_config(tmp_path, patch={"player": {"remember_progress": False}})
    player = PlayerApi(config_dir=tmp_path)
    try:
        player.select_playlist(UID)
        player.report_position(5000)
    finally:
        player.close()

    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["player"]["last_position_ms"] == 0


def test_pick_loop_song_outside_the_playlist(tmp_path):
    write_config(tmp_path, extra=("e",))
    player = PlayerApi(config_dir=tmp_path)
    try:
        player.select_playlist(UID)
        data = player.pick_loop_song(md5("e"))

        assert data["mode"] == "repeat_one"
        assert data["track"]["md5"] == md5("e")
        assert data["queue"]["pinned"] == "Song e"

        back = player.set_mode("list_loop")
        assert back["track"]["md5"] == md5("a")
        assert back["queue"]["pinned"] is None
    finally:
        player.close()


def test_track_failed_moves_to_the_next(api):
    api.select_playlist(UID)
    data = api.track_failed(md5("a"), "media")

    assert data["track"]["md5"] == md5("b")
    assert data["notice"]["text"].startswith("Song a")


def test_list_songs_searches_names(api):
    api.select_playlist(UID)
    result = api.list_songs("song b")

    assert [item["md5"] for item in result["items"]] == [md5("b")]
    assert result["items"][0]["in_playlist"] is True


def test_ui_tokens_match():
    def names(text: str) -> set[str]:
        block = text.split(":root {", 1)[1].split("}", 1)[0]
        return set(re.findall(r"(--[\w-]+)\s*:", block))

    manager = (paths.UI_MANAGER_DIR / "styles.css").read_text(encoding="utf-8")
    player = (paths.UI_PLAYER_DIR / "styles.css").read_text(encoding="utf-8")
    assert names(manager) == names(player)
