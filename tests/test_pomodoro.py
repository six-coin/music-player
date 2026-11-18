"""番茄钟的数据模型、统计与资源引用。"""

from __future__ import annotations

import json

import pytest

from app.core.pomodoro import (
    AudioAsset,
    Background,
    PomodoroStore,
    TimeStats,
)
from app.errors import DataError
from app.models import new_uid


@pytest.fixture
def store(tmp_path) -> PomodoroStore:
    store = PomodoroStore(tmp_path / "pomodoro.json")
    assert store.load() == []
    return store


def test_default_modes_are_created(store):
    modes = store.mode_list()

    assert [mode.name for mode in modes] == ["经典番茄", "深度专注"]
    assert modes[0].segments == [25, 5, 25, 5, 25, 5, 25]
    assert modes[1].segments == [50, 10, 50]
    assert (store.path).exists()


def test_create_item_uses_a_valid_mode_and_defaults(store):
    item = store.create_item("晨间")

    assert item.duration_mode in store.duration_modes
    assert item.focus.play is True
    assert item.rest.play is False
    assert item.background_mode == "cover"
    assert item.font == "system"
    assert item.to_dict()["uid"] == item.uid


def test_update_item_rejects_unknown_mode(store):
    item = store.create_item("晨间")

    with pytest.raises(DataError):
        store.update_item(item.uid, {"duration_mode": "f" * 32})


def test_stats_are_parallel_and_total_survives_delete(store):
    item = store.create_item("晨间")
    store.add_time(item.uid, focus_ms=1500_000, rest_ms=300_000, completed=True)

    assert store.total.focus_ms == 1500_000
    assert store.total.rest_ms == 300_000
    assert store.total.sessions == 1
    assert store.stats_for(item.uid).focus_ms == 1500_000

    assert store.delete_item(item.uid) is True
    assert store.total.focus_ms == 1500_000
    assert store.total.sessions == 1
    assert store.stats_for(item.uid) == TimeStats()


def test_time_for_a_deleted_item_only_counts_in_total(store):
    item = store.create_item("晨间")
    store.delete_item(item.uid)

    store.add_time(item.uid, focus_ms=1000, rest_ms=0)

    assert store.total.focus_ms == 1000
    assert item.uid not in store.item_stats


def test_last_mode_cannot_be_deleted(store):
    for mode in list(store.duration_modes.values()):
        if len(store.duration_modes) > 1:
            assert store.delete_mode(mode.uid) is True

    only = store.mode_list()[0]
    assert store.delete_mode(only.uid) is False
    assert store.mode_list() == [only]


def test_deleting_a_mode_falls_back_to_another(store):
    item = store.create_item("晨间")
    old = item.duration_mode
    replacement = next(mode.uid for mode in store.mode_list() if mode.uid != old)

    assert store.delete_mode(old) is True
    assert store.find_item(item.uid).duration_mode == replacement


def test_deleting_a_background_clears_references(store):
    item = store.create_item("晨间")
    background = Background(
        uid=new_uid(),
        name="海边",
        file="pomodoro/background/x.png",
        kind="image",
        size=10,
    )
    store.add_background(background)
    store.update_item(item.uid, {"background": background.uid})

    removed = store.delete_background(background.uid)

    assert removed is not None
    assert store.find_item(item.uid).background is None


def test_deleting_an_environment_disables_it(store):
    item = store.create_item("晨间")
    environment = AudioAsset(
        uid=new_uid(),
        name="雨声",
        file="pomodoro/environment/x.mp3",
        ext="mp3",
    )
    store.add_environment(environment)
    store.update_item(
        item.uid,
        {"environment": environment.uid, "environment_enabled": True},
    )

    store.delete_environment(environment.uid)

    assert store.find_item(item.uid).environment is None
    assert store.find_item(item.uid).environment_enabled is False


def test_reorder_keeps_everything(store):
    first = store.create_item("一")
    second = store.create_item("二")

    store.reorder_items([second.uid, first.uid])

    assert [item.uid for item in store.item_list()] == [second.uid, first.uid]


def test_playlist_references_are_cleared(store):
    item = store.create_item("晨间")
    playlist = "a" * 32
    store.update_item(
        item.uid,
        {"focus": {"playlist": playlist, "play": True, "order": "list_loop"}},
    )

    assert store.sanitize_playlists(set()) == 1
    assert store.find_item(item.uid).focus.playlist is None
    assert store.find_item(item.uid).focus.order == "list_loop"


def test_payload_roundtrip(tmp_path):
    first = PomodoroStore(tmp_path / "pomodoro.json")
    first.load()
    item = first.create_item("晨间")
    first.add_time(item.uid, focus_ms=1234, rest_ms=56, completed=True)
    first.set_volumes(0.7, 0.2)
    first.set_hud_scale(2.1)

    second = PomodoroStore(tmp_path / "pomodoro.json")
    assert second.load() == []
    assert second.find_item(item.uid).name == "晨间"
    assert second.total.focus_ms == 1234
    assert second.total.rest_ms == 56
    assert second.music_volume == 0.7
    assert second.environment_volume == 0.2
    assert second.hud_scale == 2.1


def test_hud_scale_default_and_clamp(store):
    assert store.hud_scale == 1.5

    store.set_hud_scale(9)
    assert store.hud_scale == 3.0
    store.set_hud_scale(0)
    assert store.hud_scale == 0.5
    store.set_hud_scale(1.8)
    assert store.hud_scale == 1.8


def test_broken_file_is_backed_up(tmp_path):
    path = tmp_path / "pomodoro.json"
    path.write_text("{ not json", encoding="utf-8")
    store = PomodoroStore(path)

    warnings = store.load()

    assert warnings
    assert path.exists()
    assert list(tmp_path.glob("pomodoro.json.bad*"))
    assert store.mode_list()


def test_segment_bounds(store):
    with pytest.raises(DataError):
        store.create_mode("空", [])

    # 越界的单段时长在 normalize() 里夹取，与设置文件的处理一致。
    assert store.create_mode("太长", [181]).segments == [180]
    assert store.create_mode("太短", [0]).segments == [1]
    assert store.create_mode("刚好", [180]).segments == [180]


def test_stats_payload_shape(store):
    item = store.create_item("晨间")
    store.add_time(item.uid, focus_ms=10, rest_ms=20, completed=False)

    payload = json.loads(store.path.read_text(encoding="utf-8"))

    assert payload["version"] == 1
    assert payload["stats"]["total"]["focus_ms"] == 10
    assert payload["stats"]["items"][item.uid]["rest_ms"] == 20
    assert payload["items"][0]["name"] == "晨间"
