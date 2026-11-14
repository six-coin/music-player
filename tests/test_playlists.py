"""歌单的读写与解析。"""

from __future__ import annotations

import json

import pytest

from app.core.library import Library
from app.core.playlists import PlaylistStore
from app.errors import PlaylistCycleError
from app.models import Filter


def build_library(tmp_path, music_factory) -> Library:
    library = Library(tmp_path / "library.json")
    library.load()
    library.upsert_music(music_factory("a", tags=["d" * 32], authors=["e" * 32]))
    library.upsert_music(music_factory("b"))
    return library


def test_default_playlist_is_created(tmp_path, music_factory):
    library = build_library(tmp_path, music_factory)
    store = PlaylistStore(tmp_path / "playlists.json")

    store.load()

    default = store.default()
    assert default.builtin is True
    assert default.name is None
    assert store.default_uid == default.uid
    assert store.resolve(default.uid, library).as_set() == {"a" * 32, "b" * 32}


def test_manual_playlist_keeps_order(tmp_path, music_factory):
    library = build_library(tmp_path, music_factory)
    store = PlaylistStore(tmp_path / "playlists.json")
    store.load()
    playlist = store.create("深夜", "manual")
    playlist.entries = ["b" * 32, "a" * 32]

    content = store.resolve(playlist.uid, library)

    assert content.md5s == ["b" * 32, "a" * 32]
    assert content.ordered is True


def test_manual_playlist_skips_unknown_songs(tmp_path, music_factory):
    library = build_library(tmp_path, music_factory)
    store = PlaylistStore(tmp_path / "playlists.json")
    store.load()
    playlist = store.create("深夜", "manual")
    playlist.entries = ["f" * 32, "a" * 32]

    assert store.resolve(playlist.uid, library).md5s == ["a" * 32]


def test_filter_include_tag(tmp_path, music_factory):
    library = build_library(tmp_path, music_factory)
    store = PlaylistStore(tmp_path / "playlists.json")
    store.load()
    playlist = store.create("古典", "filter")
    playlist.filters = [Filter(mode="include", target="tag", values=["d" * 32])]

    content = store.resolve(playlist.uid, library)

    assert content.md5s == ["a" * 32]
    assert content.ordered is False


def test_filter_include_all_then_exclude_tag(tmp_path, music_factory):
    library = build_library(tmp_path, music_factory)
    store = PlaylistStore(tmp_path / "playlists.json")
    store.load()
    playlist = store.create("非古典", "filter")
    playlist.filters = [
        Filter(mode="include", target="all"),
        Filter(mode="exclude", target="tag", values=["d" * 32]),
    ]

    assert store.resolve(playlist.uid, library).md5s == ["b" * 32]


def test_filter_by_author(tmp_path, music_factory):
    library = build_library(tmp_path, music_factory)
    store = PlaylistStore(tmp_path / "playlists.json")
    store.load()
    playlist = store.create("某作者", "filter")
    playlist.filters = [Filter(mode="include", target="author", values=["e" * 32])]

    assert store.resolve(playlist.uid, library).md5s == ["a" * 32]


def test_nested_playlist_is_resolved(tmp_path, music_factory):
    library = build_library(tmp_path, music_factory)
    store = PlaylistStore(tmp_path / "playlists.json")
    store.load()
    inner = store.create("内层", "filter")
    inner.filters = [Filter(mode="include", target="tag", values=["d" * 32])]
    outer = store.create("外层", "filter")
    outer.filters = [Filter(mode="include", target="playlist", values=[inner.uid])]

    assert store.resolve(outer.uid, library).md5s == ["a" * 32]


def test_cycle_is_detected(tmp_path, music_factory):
    library = build_library(tmp_path, music_factory)
    store = PlaylistStore(tmp_path / "playlists.json")
    store.load()
    first = store.create("一", "filter")
    second = store.create("二", "filter")
    first.filters = [Filter(mode="include", target="playlist", values=[second.uid])]
    second.filters = [Filter(mode="include", target="playlist", values=[first.uid])]

    with pytest.raises(PlaylistCycleError):
        store.resolve(first.uid, library)


def test_builtin_playlist_cannot_be_removed(tmp_path):
    store = PlaylistStore(tmp_path / "playlists.json")
    store.load()

    assert store.remove(store.default_uid) is False


def test_broken_default_uid_is_repaired(tmp_path):
    path = tmp_path / "playlists.json"
    path.write_text(
        '{"version": 1, "default_uid": "missing", "items": []}',
        encoding="utf-8",
    )

    store = PlaylistStore(path)
    store.load()

    assert store.default_uid in store.items
    assert store.default().builtin is True


def test_filter_playlist_keeps_at_least_one_condition(tmp_path):
    """删掉最后一条条件后补回默认条件：文件不能变成加载时会被丢掉的坏记录。"""
    store = PlaylistStore(tmp_path / "playlists.json")
    store.load()
    playlist = store.create("条件", "filter")
    playlist.filters = []

    playlist.normalize()
    playlist.validate()

    assert len(playlist.filters) == 1
    assert playlist.filters[0].target == "all"


def test_default_playlist_is_persisted_when_missing(tmp_path):
    """文件里没有内置歌单时，新建的那条要立刻落盘，否则每次启动都会换 uid。"""
    path = tmp_path / "playlists.json"
    path.write_text(json.dumps({"version": 1, "default_uid": "", "items": []}), encoding="utf-8")

    store = PlaylistStore(path)
    store.load()

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["default_uid"] == store.default_uid
    assert [item["builtin"] for item in saved["items"]] == [True]
