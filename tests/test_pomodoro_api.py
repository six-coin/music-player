"""番茄钟的 JS 桥：快照、选择、开始、统计与会话级覆盖。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import paths
from app.core.pomodoro import AudioAsset, Background
from app.models import new_uid
from app.settings import defaults
from app.ui.manager.api import ManagerApi
from app.ui.player.api import PlayerApi

UID = "d" * 32
MD5 = "a" * 32


def write_config(tmp_path: Path) -> None:
    library = {
        "version": 1,
        "authors": [],
        "tag_groups": [],
        "musics": [
            {
                "md5": MD5,
                "names": ["Song a"],
                "authors": [],
                "tags": [],
                "ext": "mp3",
                "duration_ms": 1000,
            }
        ],
    }
    playlists = {
        "version": 1,
        "default_uid": UID,
        "items": [
            {
                "uid": UID,
                "name": None,
                "builtin": True,
                "kind": "manual",
                "entries": [MD5],
                "filters": [],
                "adaptation": {"enabled": True},
            }
        ],
    }
    (tmp_path / "library.json").write_text(json.dumps(library), encoding="utf-8")
    (tmp_path / "playlists.json").write_text(json.dumps(playlists), encoding="utf-8")
    (tmp_path / "settings.json").write_text(json.dumps(defaults()), encoding="utf-8")
    music = paths.music_path(MD5, "mp3")
    music.parent.mkdir(parents=True, exist_ok=True)
    music.write_bytes(b"fake")


def touch_asset(relative: str) -> None:
    path = paths.data_path(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake")


@pytest.fixture
def manager(tmp_path):
    write_config(tmp_path)
    api = ManagerApi(config_dir=tmp_path)
    yield api
    api.close()


@pytest.fixture
def player(tmp_path):
    write_config(tmp_path)
    api = PlayerApi(config_dir=tmp_path)
    yield api
    api.close()


def test_manager_snapshot_has_pomodoro_payload(manager):
    payload = manager.get_state()["pomodoro"]

    assert payload["items"] == []
    assert [mode["name"] for mode in payload["duration_modes"]] == ["经典番茄", "深度专注"]
    assert payload["overview"]["total"]["focus_ms"] == 0


def test_manager_creates_selects_and_deletes(manager):
    created = manager.create_pomodoro("晨间")
    item = created["pomodoro"]["items"][0]

    assert created["section"] == "pomodoro"
    assert created["selection"] == {"kind": "pomodoro", "uid": item["uid"]}
    assert item["summary"] == "25/5/25/5/25/5/25"

    updated = manager.update_pomodoro(item["uid"], {"description": "说明"})
    assert updated["pomodoro"]["items"][0]["description"] == "说明"

    deleted = manager.delete_pomodoro(item["uid"])
    assert deleted["pomodoro"]["items"] == []
    assert deleted["selection"]["kind"] == "pomodoro_overview"


def test_manager_keeps_at_least_one_duration_mode(manager):
    for mode in list(manager.pomodoro.duration_modes.values())[:-1]:
        assert manager.delete_duration_mode(mode.uid)["ok"] is True

    last = manager.pomodoro.mode_list()[0]
    result = manager.delete_duration_mode(last.uid)

    assert result["ok"] is False
    assert result["message"]
    assert len(manager.pomodoro.duration_modes) == 1


def test_manager_delete_background_clears_item_reference(manager):
    item = manager.pomodoro.create_item("晨间")
    background = Background(
        uid=new_uid(),
        name="海边",
        file="pomodoro/background/x.png",
        kind="image",
        size=10,
    )
    manager.pomodoro.add_background(background)
    manager.update_pomodoro(item.uid, {"background": background.uid})

    result = manager.delete_background(background.uid)

    assert result["ok"] is True
    assert result["pomodoro"]["items"][0]["background"] is None


def test_manager_switching_to_pomodoro_works_with_no_selection(manager):
    """刚启动、什么都没选时 selection 是 None，进番茄分区不能炸。"""
    assert manager.selection is None

    data = manager.select_section("pomodoro")

    assert data["section"] == "pomodoro"
    assert data["selection"] == {"kind": "pomodoro_overview", "uid": ""}


def test_manager_switching_to_pomodoro_selects_the_overview(manager):
    manager.select_item("music", MD5)
    assert manager.get_state()["selection"]["kind"] == "music"

    data = manager.select_section("pomodoro")

    assert data["section"] == "pomodoro"
    assert data["selection"] == {"kind": "pomodoro_overview", "uid": ""}


def test_manager_keeps_a_pomodoro_selection_when_coming_back(manager):
    created = manager.create_pomodoro("晨间")
    uid = created["selection"]["uid"]
    manager.select_section("songs")

    data = manager.select_section("pomodoro")

    assert data["selection"] == {"kind": "pomodoro", "uid": uid}


def test_manager_hud_scale_is_shared_with_the_player(manager):
    assert manager.get_state()["pomodoro"]["preferences"]["hud_scale"] == 1.0

    data = manager.set_pomodoro_hud_scale(1.4)

    assert data["pomodoro"]["preferences"]["hud_scale"] == 1.4
    assert data["pomodoro"]["preferences"]["hud_scale_min"] == 0.2
    assert data["pomodoro"]["preferences"]["hud_scale_max"] == 5.0


def test_manager_hud_scale_is_clamped(manager):
    assert manager.set_pomodoro_hud_scale(99)["pomodoro"]["preferences"]["hud_scale"] == 5.0
    assert manager.set_pomodoro_hud_scale(0)["pomodoro"]["preferences"]["hud_scale"] == 0.2


def test_player_phase_without_a_playlist_plays_nothing(player):
    item = player.pomodoro.create_item("晨间")
    player.pomodoro.update_item(item.uid, {"focus": {"playlist": UID}})
    player.pomodoro_start(item.uid, {"focus": {"playlist": ""}})

    phase = player.pomodoro_phase(0)

    assert phase == {"ok": True, "phase": "focus", "play": False}


def test_player_snapshot_lists_pomodoros(player):
    item = player.pomodoro.create_item("晨间")
    player.pomodoro.update_item(item.uid, {"focus": {"playlist": UID}})

    data = player.get_state()

    assert data["pomodoros"]["items"][0]["name"] == "晨间"
    assert data["pomodoros"]["selected"] is None


def test_player_starts_phase_and_records(player):
    item = player.pomodoro.create_item("晨间")
    player.pomodoro.update_item(
        item.uid,
        {"focus": {"playlist": UID, "order": "shuffle"}},
    )

    started = player.pomodoro_start(item.uid, {})
    assert started["ok"] is True
    assert started["plan"]["segments"] == [25, 5, 25, 5, 25, 5, 25]
    assert started["plan"]["focus"]["playlist"] == UID

    phase = player.pomodoro_phase(0)
    assert phase["ok"] is True
    assert phase["play"] is True
    assert phase["command"]["kind"] == "load"
    assert phase["command"]["url"].startswith("http://127.0.0.1:")

    player.pomodoro_report(item.uid, 1500_000, 300_000, True)
    stats = player.get_state()["pomodoros"]["selected"]["stats"]
    assert stats["focus_ms"] == 1500_000
    assert stats["rest_ms"] == 300_000
    assert stats["sessions"] == 1

    finished = player.pomodoro_finish(item.uid)
    assert finished["pomodoros"]["active"] is None


def test_player_overrides_do_not_change_the_stored_item(player):
    item = player.pomodoro.create_item("晨间")
    background = Background(
        uid=new_uid(),
        name="海边",
        file="pomodoro/background/x.png",
        kind="image",
        size=10,
    )
    player.pomodoro.add_background(background)
    touch_asset(background.file)

    started = player.pomodoro_start(
        item.uid,
        {
            "background": background.uid,
            "background_mode": "contain",
            "font": "kai",
        },
    )

    assert started["plan"]["background"]["kind"] == "image"
    assert started["plan"]["background_mode"] == "contain"
    assert started["plan"]["font"] == "kai"
    stored = player.pomodoro.find_item(item.uid)
    assert stored.background is None
    assert stored.background_mode == "cover"
    assert stored.font == "system"
    assert stored.environment is None


def test_player_selecting_a_pomodoro_clears_the_playlist(player):
    """点番茄钟后主区域换成详情：歌单高亮、当前曲、播放状态都要收掉。"""
    item = player.pomodoro.create_item("晨间")
    player.select_playlist(UID)
    assert player.get_state()["playlist_uid"] == UID

    data = player.select_pomodoro(item.uid)

    assert data["playlist_uid"] is None
    assert data["track"] is None
    assert [entry["active"] for entry in data["playlists"]] == [False]
    assert data["command"]["kind"] == "stop"
    assert data["pomodoros"]["selected"]["uid"] == item.uid
    # 只是收掉界面状态，不覆盖上次听的那张歌单：重启还要停回原处。
    assert player.settings.get("player", "last_playlist", default=None) == UID


def test_player_selecting_a_playlist_leaves_the_pomodoro_detail(player):
    item = player.pomodoro.create_item("晨间")
    player.select_pomodoro(item.uid)
    assert player.get_state()["pomodoros"]["selected"]["uid"] == item.uid

    data = player.select_playlist(UID)

    assert data["pomodoros"]["selected"] is None


def test_player_applies_the_phase_order_with_the_same_playlist(player):
    item = player.pomodoro.create_item("晨间")
    player.pomodoro.update_item(
        item.uid,
        {
            "focus": {"playlist": UID, "order": "shuffle"},
            "rest": {"playlist": UID, "order": "list_loop"},
        },
    )

    player.pomodoro_start(item.uid, {})
    player.pomodoro_phase(0)
    player.pomodoro_phase(1)

    assert player._pomo_session.mode == "list_loop"


def test_player_hud_scale_is_a_global_preference(player):
    item = player.pomodoro.create_item("晨间")

    assert player.pomodoro_set_hud_scale(1.8)["ok"] is True
    plan = player.pomodoro_start(item.uid, {})["plan"]

    assert plan["hud_scale"] == 1.8
    assert player.get_state()["pomodoros"]["preferences"]["hud_scale"] == 1.8


def test_player_cannot_start_twice(player):
    item = player.pomodoro.create_item("晨间")

    assert player.pomodoro_start(item.uid, {})["ok"] is True
    assert player.pomodoro_start(item.uid, {})["ok"] is False


def test_player_ring_and_environment_urls(player):
    item = player.pomodoro.create_item("晨间")
    ring = AudioAsset(
        uid=new_uid(),
        name="木鱼",
        file="pomodoro/ring/x.mp3",
        ext="mp3",
    )
    environment = AudioAsset(
        uid=new_uid(),
        name="雨声",
        file="pomodoro/environment/x.mp3",
        ext="mp3",
    )
    player.pomodoro.add_ring(ring)
    player.pomodoro.add_environment(environment)
    touch_asset(ring.file)
    touch_asset(environment.file)
    player.pomodoro.update_item(
        item.uid,
        {"ring": ring.uid, "environment": environment.uid},
    )

    plan = player.pomodoro_start(item.uid, {})["plan"]

    assert plan["ring"]["url"].startswith("http://127.0.0.1:")
    assert plan["environment"]["url"].startswith("http://127.0.0.1:")
