"""歌单的编辑与解析接口。"""

from __future__ import annotations

import pytest

from app.models import Author, Tag, TagGroup
from app.ui.manager.api import ManagerApi

SONG_A = "a" * 32
SONG_B = "b" * 32
TAG = "d" * 32
AUTHOR = "e" * 32


@pytest.fixture
def api(tmp_path, music_factory):
    instance = ManagerApi(config_dir=tmp_path)
    instance.library.upsert_music(
        music_factory("a", names=["Song a"], tags=[TAG], authors=[AUTHOR])
    )
    instance.library.upsert_music(music_factory("b", names=["Song b"]))
    instance.library.upsert_tag_group(TagGroup(uid="c" * 32, name="风格", tags=[Tag(TAG, "古典")]))
    instance.library.upsert_author(Author(uid=AUTHOR, name="Alice"))
    instance.library.save()
    return instance


def test_create_manual_playlist(api):
    state = api.create_playlist("深夜", "manual")

    assert state["section"] == "playlists"
    assert state["selection"]["kind"] == "playlist"
    created = api.playlists.get(state["selection"]["uid"])
    assert created.kind == "manual"
    assert created.entries == []


def test_create_rejects_empty_name(api):
    state = api.create_playlist("   ", "manual")

    assert state["ok"] is False


def test_rename_playlist(api):
    playlist = api.playlists.create("旧名", "manual")

    assert api.update_playlist_name(playlist.uid, " 新名 ") == {"ok": True}
    assert playlist.name == "新名"
    assert api.update_playlist_name(playlist.uid, "  ") == {"ok": False}


def test_builtin_playlist_cannot_be_renamed(api):
    default = api.playlists.default()

    assert api.update_playlist_name(default.uid, "改名") == {"ok": False}


def test_playlists_can_be_reordered(api):
    first = api.playlists.create("甲", "manual")
    second = api.playlists.create("乙", "manual")
    third = api.playlists.create("丙", "manual")

    state = api.reorder_playlists([third.uid, first.uid, second.uid])

    assert [item["uid"] for item in state["playlists"]] == [
        third.uid,
        first.uid,
        second.uid,
        api.playlists.default().uid,
    ]


def test_set_entries_keeps_order_and_drops_unknown(api):
    playlist = api.playlists.create("深夜", "manual")

    api.set_playlist_entries(playlist.uid, [SONG_B, "f" * 32, SONG_A, SONG_B])

    assert playlist.entries == [SONG_B, SONG_A]


def test_add_and_remove_songs(api):
    playlist = api.playlists.create("深夜", "manual")

    api.add_playlist_songs(playlist.uid, [SONG_A, SONG_A])
    api.add_playlist_songs(playlist.uid, [SONG_B])
    assert playlist.entries == [SONG_A, SONG_B]

    api.remove_playlist_song(playlist.uid, SONG_A)
    assert playlist.entries == [SONG_B]


def test_editing_playlist_tracks_keeps_their_stats(api):
    """歌单增删曲目不动自适应数据：冗余可以接受，重新加回来还能接上。"""
    playlist = api.playlists.create("深夜", "manual")
    api.add_playlist_songs(playlist.uid, [SONG_A, SONG_B])
    api.stats.record(playlist.uid, SONG_A, skipped=False, window=100)
    api.stats.record(playlist.uid, SONG_A, skipped=True, window=100)

    api.remove_playlist_song(playlist.uid, SONG_A)
    api.set_playlist_entries(playlist.uid, [SONG_B])

    entry = api.stats.load(playlist.uid)[SONG_A]
    assert entry.records == "01"
    assert entry.full_plays == 1


def test_filter_crud(api):
    playlist = api.playlists.create("条件", "filter")
    assert len(playlist.filters) == 1

    api.add_filter(playlist.uid)
    assert len(playlist.filters) == 2

    api.update_filter(playlist.uid, 1, {"mode": "exclude", "target": "tag", "values": [TAG]})
    assert playlist.filters[1].mode == "exclude"
    assert playlist.filters[1].target == "tag"
    assert playlist.filters[1].values == [TAG]

    api.update_filter(playlist.uid, 1, {"target": "all"})
    assert playlist.filters[1].values == []

    api.move_filter(playlist.uid, 1, -1)
    assert playlist.filters[0].target == "all"

    api.remove_filter(playlist.uid, 0)
    assert len(playlist.filters) == 1


def test_delete_manual_playlist_clears_selection(api):
    playlist = api.playlists.create("深夜", "manual")
    api.select_item("playlist", playlist.uid)

    state = api.delete_playlist(playlist.uid)

    assert api.playlists.get(playlist.uid) is None
    assert state["selection"] is None


def test_builtin_playlist_cannot_be_deleted(api):
    default = api.playlists.default()

    api.delete_playlist(default.uid)

    assert api.playlists.get(default.uid) is not None


def test_referenced_playlist_cannot_be_deleted(api):
    target = api.playlists.create("被引用", "manual")
    holder = api.playlists.create("引用者", "filter")
    api.update_filter(holder.uid, 0, {"target": "playlist", "values": [target.uid]})

    state = api.delete_playlist(target.uid)

    assert state["ok"] is False
    assert api.playlists.get(target.uid) is not None


def test_get_playlist_songs(api):
    playlist = api.playlists.create("全部", "filter")

    result = api.get_playlist_songs(playlist.uid)

    assert result["ok"] is True
    assert {item["md5"] for item in result["items"]} == {SONG_A, SONG_B}


def test_get_playlist_songs_reports_cycle(api):
    first = api.playlists.create("一", "filter")
    second = api.playlists.create("二", "filter")
    api.update_filter(first.uid, 0, {"target": "playlist", "values": [second.uid]})
    api.update_filter(second.uid, 0, {"target": "playlist", "values": [first.uid]})

    result = api.get_playlist_songs(first.uid)

    assert result["ok"] is False
    assert "循环" in result["message"]


def test_select_playlist_switches_section(api):
    playlist = api.playlists.create("深夜", "manual")

    state = api.select_item("playlist", playlist.uid)

    assert state["section"] == "playlists"
    assert state["selection"] == {"kind": "playlist", "uid": playlist.uid}
