"""番茄钟的 JS 桥：快照、选择、开始、统计与会话级覆盖。"""

from __future__ import annotations

import json
import time
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

    data = manager.set_pomodoro_preferences({"hud_scale": 1.4})

    assert data["pomodoro"]["preferences"]["hud_scale"] == 1.4
    assert data["pomodoro"]["preferences"]["hud_scale_min"] == 0.2
    assert data["pomodoro"]["preferences"]["hud_scale_max"] == 5.0


def test_manager_hud_scale_is_clamped(manager):
    data = manager.set_pomodoro_preferences({"hud_scale": 99})
    assert data["pomodoro"]["preferences"]["hud_scale"] == 5.0

    data = manager.set_pomodoro_preferences({"hud_scale": 0})
    assert data["pomodoro"]["preferences"]["hud_scale"] == 0.2


def test_manager_rhythm_preferences_roundtrip(manager):
    data = manager.set_pomodoro_preferences(
        {"prep_seconds": 0, "duck_ms": 5000, "duck_ratio": 0.3, "fade_in_ms": 0}
    )
    preferences = data["pomodoro"]["preferences"]

    assert preferences["prep_seconds"] == 0
    assert preferences["duck_ms"] == 5000
    assert preferences["duck_ratio"] == 0.3
    assert preferences["fade_in_ms"] == 0
    assert preferences["prep_seconds_max"] == 300


def test_manager_updates_asset_descriptions(manager):
    background = Background(
        uid=new_uid(),
        name="海边",
        file="pomodoro/background/x.png",
        kind="image",
    )
    manager.pomodoro.add_background(background)

    assert manager.update_pomodoro_asset("background", background.uid, {"description": "夜里"})[
        "ok"
    ]

    payload = manager.get_state()["pomodoro"]
    assert payload["backgrounds"][0]["description"] == "夜里"
    assert payload["backgrounds"][0]["name"] == "海边"


def test_manager_sees_the_sessions_the_player_wrote(manager, player):
    item = player.pomodoro.create_item("晨间")
    assert player.pomodoro_record_session(item.uid, 1_790_000_000, 1500_000, 300_000)["ok"]

    sessions = manager.get_state()["pomodoro"]["sessions"]

    assert len(sessions) == 1
    assert sessions[0]["uid"] == item.uid
    assert sessions[0]["focus_ms"] == 1500_000
    assert sessions[0]["rest_ms"] == 300_000
    assert sessions[0]["started_at"] == 1_790_000_000


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


def test_player_plan_carries_the_rhythm_preferences(player):
    item = player.pomodoro.create_item("晨间")
    player.pomodoro.set_preferences(
        {"prep_seconds": 0, "duck_ms": 3000, "duck_ratio": 0.2, "fade_in_ms": 700}
    )

    plan = player.pomodoro_start(item.uid, {})["plan"]

    assert plan["prep_seconds"] == 0
    assert plan["duck_ms"] == 3000
    assert plan["duck_ratio"] == 0.2
    assert plan["fade_in_ms"] == 700


def test_player_records_a_session_with_a_fallback_start(player):
    item = player.pomodoro.create_item("晨间")

    assert player.pomodoro_record_session(item.uid, 0, 60_000, 30_000)["ok"] is True

    record = player.pomo_sessions.entries()[0]
    assert record.uid == item.uid
    assert record.started_at <= record.ended_at
    assert (record.focus_ms, record.rest_ms) == (60_000, 30_000)


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


def test_window_close_is_blocked_until_the_run_ends(player):
    item = player.pomodoro.create_item("晨间")

    assert player.pomodoro_start(item.uid, {})["ok"] is True
    # 计时中：X / Alt+F4 被拦下，交给页面确认。
    assert player.on_closing() is False
    assert player.pomodoro_running() is True

    # 走完一轮进完成页：已经结束了，不该再拦。
    player.pomodoro_report(item.uid, 1000, 0, True)
    assert player.pomodoro_running() is False
    assert player.on_closing() is True


def test_force_close_marks_the_close_as_confirmed(player):
    item = player.pomodoro.create_item("晨间")
    player.pomodoro_start(item.uid, {})

    player.force_close()

    assert player.on_closing() is True


class FakeWindow:
    """只记录 pywebview 被要求做了什么。"""

    def __init__(self) -> None:
        self.scripts: list[str] = []
        self.destroyed = False

    def evaluate_js(self, script: str) -> bool:
        self.scripts.append(script)
        return True

    def destroy(self) -> None:
        self.destroyed = True


def test_close_prompt_is_pushed_to_the_page(player):
    item = player.pomodoro.create_item("晨间")
    player.pomodoro_start(item.uid, {})
    window = FakeWindow()
    player.attach(window)

    assert player.on_closing() is False
    deadline = time.time() + 2
    while not window.scripts and time.time() < deadline:
        time.sleep(0.01)
    assert window.scripts and "pomoAskClose" in window.scripts[0]

    player.force_close()
    assert window.destroyed is True


REST_UID = "e" * 32
REST_MD5 = "b" * 32


def add_rest_playlist(root: Path) -> None:
    library = json.loads((root / "library.json").read_text(encoding="utf-8"))
    library["musics"].append(
        {
            "md5": REST_MD5,
            "names": ["Song b"],
            "authors": [],
            "tags": [],
            "ext": "mp3",
            "duration_ms": 1000,
        }
    )
    (root / "library.json").write_text(json.dumps(library), encoding="utf-8")
    playlists = json.loads((root / "playlists.json").read_text(encoding="utf-8"))
    playlists["items"].append(
        {
            "uid": REST_UID,
            "name": "休息",
            "builtin": False,
            "kind": "manual",
            "entries": [REST_MD5],
            "filters": [],
            "adaptation": {"enabled": True},
        }
    )
    (root / "playlists.json").write_text(json.dumps(playlists), encoding="utf-8")
    music = paths.music_path(REST_MD5, "mp3")
    music.parent.mkdir(parents=True, exist_ok=True)
    music.write_bytes(b"fake")


def test_phase_switch_resumes_the_unfinished_track(tmp_path):
    write_config(tmp_path)
    add_rest_playlist(tmp_path)
    api = PlayerApi(config_dir=tmp_path)
    try:
        item = api.pomodoro.create_item("晨间")
        api.pomodoro.update_item(
            item.uid,
            {
                "focus": {"playlist": UID, "order": "list_loop"},
                "rest": {"playlist": REST_UID, "order": "list_loop"},
            },
        )
        assert api.pomodoro_start(item.uid, {})["ok"] is True

        first = api.pomodoro_phase(0)
        assert first["play"] is True
        assert first["command"]["md5"] == MD5

        # 专注结束：网页报回停在哪；休息放另一张歌单。
        rest = api.pomodoro_phase(1, None, {"md5": MD5, "position_ms": 42_000})
        assert rest["command"]["md5"] == REST_MD5

        # 切回专注：接着放上次没播完的那首，位置也对上。
        back = api.pomodoro_phase(2, None, {"md5": REST_MD5, "position_ms": 5_000})
        assert back["command"]["md5"] == MD5
        assert back["command"]["position_ms"] == 42_000
        assert back["command"]["autoplay"] is True
    finally:
        api.close()


def test_phase_end_leaves_the_last_track_unrecorded(tmp_path):
    """后面还有同一张歌单的段：最后一首一首都不记，下一段接着放。"""
    write_config(tmp_path)
    add_rest_playlist(tmp_path)
    api = PlayerApi(config_dir=tmp_path)
    try:
        item = api.pomodoro.create_item("晨间")
        api.pomodoro.update_item(
            item.uid,
            {
                "focus": {"playlist": UID, "order": "list_loop"},
                "rest": {"playlist": REST_UID, "order": "list_loop"},
            },
        )
        assert api.pomodoro_start(item.uid, {})["ok"] is True
        assert api.pomodoro_phase(0)["command"]["md5"] == MD5

        left = api.pomodoro_leave_phase({"md5": MD5, "position_ms": 42_000, "played_ms": 42_000})

        assert left == {"ok": True, "recorded": False}
        assert api.stats.load(UID) == {}
        assert api.totals.get(MD5) == 0

        # 休息放另一张歌单，切回专注时还是那首，位置与计时器都接着上一段。
        rest = api.pomodoro_phase(1, None, {"md5": MD5, "position_ms": 42_000, "played_ms": 42_000})
        assert rest["command"]["md5"] == REST_MD5

        back = api.pomodoro_phase(
            2, None, {"md5": REST_MD5, "position_ms": 5_000, "played_ms": 5_000}
        )
        assert back["command"]["md5"] == MD5
        assert back["command"]["position_ms"] == 42_000
        assert back["command"]["played_ms"] == 42_000
    finally:
        api.close()


def test_resumed_track_is_counted_once_at_the_end(tmp_path):
    """三段：专注放一半换段，最后一段接着放完，整首只算一遍。"""
    write_config(tmp_path)
    add_rest_playlist(tmp_path)
    api = PlayerApi(config_dir=tmp_path)
    try:
        mode = api.pomodoro.create_mode("三段", [25, 5, 25])
        item = api.pomodoro.create_item("晨间")
        api.pomodoro.update_item(
            item.uid,
            {
                "duration_mode": mode.uid,
                "focus": {"playlist": UID, "order": "list_loop"},
                "rest": {"playlist": REST_UID, "order": "list_loop"},
            },
        )
        assert api.pomodoro_start(item.uid, {})["ok"] is True
        assert api.pomodoro_phase(0)["command"]["md5"] == MD5

        # 第一段专注：20 秒就换段，后面还有专注段，先不记。
        first = api.pomodoro_leave_phase({"md5": MD5, "position_ms": 20_000, "played_ms": 20_000})
        assert first == {"ok": True, "recorded": False}

        api.pomodoro_phase(1, None, {"md5": MD5, "position_ms": 20_000, "played_ms": 20_000})
        back = api.pomodoro_phase(
            2, None, {"md5": REST_MD5, "position_ms": 3_000, "played_ms": 3_000}
        )
        assert back["command"]["played_ms"] == 20_000

        # 最后一段专注：20 秒 + 15 秒够阈值，整首算一遍。
        last = api.pomodoro_leave_phase({"md5": MD5, "position_ms": 35_000, "played_ms": 35_000})

        assert last == {"ok": True, "recorded": True}
        assert api.stats.load(UID)[MD5].full_plays == 1
        assert api.totals.get(MD5) == 1
    finally:
        api.close()


def one_segment_player(root: Path, *, skip_seconds: int | None = None) -> PlayerApi:
    """建一个只有一段的番茄钟：第 0 段就是这张歌单的最后一段。"""
    write_config(root)
    if skip_seconds is not None:
        playlists = json.loads((root / "playlists.json").read_text(encoding="utf-8"))
        playlists["items"][0]["adaptation"] = {"enabled": True, "skip_seconds": skip_seconds}
        (root / "playlists.json").write_text(json.dumps(playlists), encoding="utf-8")
    api = PlayerApi(config_dir=root)
    mode = api.pomodoro.create_mode("单段", [25])
    item = api.pomodoro.create_item("晨间")
    api.pomodoro.update_item(
        item.uid,
        {"duration_mode": mode.uid, "focus": {"playlist": UID, "order": "list_loop"}},
    )
    assert api.pomodoro_start(item.uid, {})["ok"] is True
    assert api.pomodoro_phase(0)["command"]["md5"] == MD5
    return api


def test_last_phase_counts_the_truncated_track_once(tmp_path):
    """最后一段：最后一首被结束截断，放够阈值就算一遍。"""
    api = one_segment_player(tmp_path)
    try:
        left = api.pomodoro_leave_phase({"md5": MD5, "position_ms": 31_000, "played_ms": 31_000})

        assert left == {"ok": True, "recorded": True}
        stats = api.stats.load(UID)[MD5]
        assert stats.records == "0"
        assert stats.full_plays == 1
        assert api.totals.get(MD5) == 1
    finally:
        api.close()


def test_last_phase_ignores_a_short_truncated_track(tmp_path):
    api = one_segment_player(tmp_path)
    try:
        left = api.pomodoro_leave_phase({"md5": MD5, "position_ms": 12_000, "played_ms": 12_000})

        assert left == {"ok": True, "recorded": False}
        assert api.stats.load(UID) == {}
        assert api.totals.get(MD5) == 0
    finally:
        api.close()


def test_truncated_track_uses_the_playlist_threshold(tmp_path):
    """阈值跟着歌单走：这张歌单设成 60 秒，45 秒就不算一遍。"""
    api = one_segment_player(tmp_path, skip_seconds=60)
    try:
        left = api.pomodoro_leave_phase({"md5": MD5, "position_ms": 45_000, "played_ms": 45_000})

        assert left == {"ok": True, "recorded": False}
        assert api.stats.load(UID) == {}
    finally:
        api.close()


def test_leaving_for_good_settles_the_current_track(tmp_path):
    """中途退出不会再有人接着放：按最后一段处理，够阈值就记一遍。"""
    write_config(tmp_path)
    api = PlayerApi(config_dir=tmp_path)
    try:
        item = api.pomodoro.create_item("晨间")
        api.pomodoro.update_item(item.uid, {"focus": {"playlist": UID, "order": "list_loop"}})
        assert api.pomodoro_start(item.uid, {})["ok"] is True
        assert api.pomodoro_phase(0)["command"]["md5"] == MD5

        left = api.pomodoro_leave_phase(
            {"md5": MD5, "position_ms": 40_000, "played_ms": 40_000}, True
        )

        assert left == {"ok": True, "recorded": True}
        assert api.stats.load(UID)[MD5].full_plays == 1
    finally:
        api.close()


def test_leave_phase_ignores_a_stale_track(tmp_path):
    api = one_segment_player(tmp_path)
    try:
        left = api.pomodoro_leave_phase({"md5": REST_MD5, "played_ms": 60_000})

        assert left == {"ok": True, "recorded": False}
        assert api.stats.load(UID) == {}
    finally:
        api.close()


def test_hot_switch_playlist_takes_effect_and_keeps_the_position(tmp_path):
    write_config(tmp_path)
    add_rest_playlist(tmp_path)
    api = PlayerApi(config_dir=tmp_path)
    try:
        item = api.pomodoro.create_item("晨间")
        api.pomodoro.update_item(
            item.uid,
            {
                "focus": {"playlist": UID, "order": "list_loop"},
                "rest": {"playlist": UID, "order": "list_loop"},
            },
        )
        assert api.pomodoro_start(item.uid, {})["ok"] is True
        assert api.pomodoro_phase(0)["command"]["md5"] == MD5

        switched = api.pomodoro_set_phases(
            {"playlist": REST_UID, "order": "list_loop"},
            {"playlist": UID, "order": "list_loop"},
            {"md5": MD5, "position_ms": 10_000},
        )
        assert switched["ok"] is True
        assert switched["command"]["md5"] == REST_MD5

        # 改回原歌单：按切换前记住的位置接着放。
        back = api.pomodoro_set_phases(
            {"playlist": UID, "order": "list_loop"},
            {"playlist": UID, "order": "list_loop"},
            {"md5": REST_MD5, "position_ms": 3_000},
        )
        assert back["command"]["md5"] == MD5
        assert back["command"]["position_ms"] == 10_000
    finally:
        api.close()


def test_partial_session_needs_enough_focus_time(player):
    item = player.pomodoro.create_item("晨间")
    player.pomodoro_start(item.uid, {})

    # 门槛默认 20 分钟：10 分钟不记，25 分钟记一条。
    player.pomodoro_finish(item.uid, 0, 10 * 60_000, 0)
    assert player.pomo_sessions.entries() == []

    player.pomodoro_start(item.uid, {})
    player.pomodoro_finish(item.uid, 0, 25 * 60_000, 2 * 60_000)
    records = player.pomo_sessions.entries()
    assert len(records) == 1
    assert (records[0].focus_ms, records[0].rest_ms) == (25 * 60_000, 2 * 60_000)


def test_partial_record_threshold_is_configurable(player):
    item = player.pomodoro.create_item("晨间")
    player.pomodoro.set_preferences({"record_minutes": 5})

    player.pomodoro_start(item.uid, {})
    player.pomodoro_finish(item.uid, 0, 6 * 60_000, 0)

    assert len(player.pomo_sessions.entries()) == 1


def test_completed_run_is_not_recorded_twice(player):
    item = player.pomodoro.create_item("晨间")
    player.pomodoro_start(item.uid, {})

    player.pomodoro_report(item.uid, 25 * 60_000, 0, True)
    player.pomodoro_finish(item.uid, 0, 25 * 60_000, 0)

    assert player.pomo_sessions.entries() == []
