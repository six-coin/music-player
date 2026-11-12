"""管理器接口层的编辑操作。"""

from __future__ import annotations

import pytest

from app.models import Author, Tag, TagGroup
from app.ui.manager.api import ManagerApi

SONG = "a" * 32


@pytest.fixture
def api(tmp_path, music_factory):
    instance = ManagerApi(config_dir=tmp_path)
    instance.library.upsert_music(music_factory("a", names=["Song a"]))
    instance.library.save()
    return instance


def test_select_item_switches_to_songs(api):
    state = api.select_item("music", SONG)

    assert state["section"] == "songs"
    assert state["selection"] == {"kind": "music", "uid": SONG}


def test_select_unknown_item_is_ignored(api):
    state = api.select_item("music", "f" * 32)

    assert state["selection"] is None


def test_rename_music(api):
    assert api.update_music_name(SONG, "  New name  ") == {"ok": True}
    assert api.library.musics[SONG].title == "New name"

    assert api.update_music_name(SONG, "   ") == {"ok": False}
    assert api.library.musics[SONG].title == "New name"


def test_set_authors_filters_unknown(api):
    api.library.upsert_author(Author(uid="b" * 32, name="Alice"))

    api.set_music_authors(SONG, ["b" * 32, "f" * 32, "b" * 32])

    assert api.library.musics[SONG].authors == ["b" * 32]


def test_unique_tag_group_replaces_previous(api):
    api.library.upsert_tag_group(
        TagGroup(
            uid="c" * 32,
            name="风格",
            unique=True,
            tags=[Tag("d" * 32, "古典"), Tag("e" * 32, "流行")],
        )
    )

    api.toggle_music_tag(SONG, "d" * 32, True)
    api.toggle_music_tag(SONG, "e" * 32, True)
    assert api.library.musics[SONG].tags == ["e" * 32]

    api.toggle_music_tag(SONG, "e" * 32, False)
    assert api.library.musics[SONG].tags == []


def test_batch_add_tags_can_clear_group(api):
    api.library.upsert_tag_group(
        TagGroup(
            uid="c" * 32,
            name="风格",
            tags=[Tag("d" * 32, "古典"), Tag("e" * 32, "流行")],
        )
    )
    api.library.musics[SONG].tags = ["d" * 32]

    api.batch_add_tags([SONG], ["e" * 32], clear_groups=True)

    assert api.library.musics[SONG].tags == ["e" * 32]


def test_batch_add_to_manual_playlist(api):
    manual = api.playlists.create("深夜", "manual")
    api.playlists.save()

    api.batch_add_to_playlist([SONG], manual.uid)

    assert manual.entries == [SONG]


def test_batch_add_to_filter_playlist_is_ignored(api):
    api.batch_add_to_playlist([SONG], api.playlists.default_uid)

    assert api.playlists.default().entries == []


def test_alias_add_move_remove(api):
    api.library.musics[SONG].names = ["A"]

    api.add_alias(SONG, "B")
    api.add_alias(SONG, "C")
    assert api.library.musics[SONG].names == ["A", "B", "C"]

    api.move_alias(SONG, 0, 1)
    assert api.library.musics[SONG].names == ["A", "C", "B"]

    api.remove_alias(SONG, 0)
    assert api.library.musics[SONG].names == ["A", "B"]


def test_remove_alias_never_touches_primary(api):
    api.library.musics[SONG].names = ["A", "B"]

    api.remove_alias(SONG, -1)

    assert api.library.musics[SONG].names == ["A", "B"]


def test_create_author_is_idempotent(api):
    api.create_author("Alice")
    api.create_author("Alice")

    assert len([item for item in api.library.authors.values() if item.name == "Alice"]) == 1


def test_integrity_report_shape(api):
    report = api.run_integrity()

    assert "ok" in report
    assert "sections" in report


def test_poll_unknown_task(api):
    assert api.poll_task("nope")["state"] == "missing"


def test_preview_import_parses_filename(api):
    preview = api.preview_import([r"C:\Music\Song A - Alice, Bob.mp3"])

    item = preview["items"][0]
    assert item["filename"] == "Song A - Alice, Bob.mp3"
    assert item["title"] == "Song A"
    assert item["authors"] == ["Alice", "Bob"]


def test_preview_import_without_author(api):
    preview = api.preview_import([r"C:\Music\Plain Name.m4a"])

    item = preview["items"][0]
    assert item["title"] == "Plain Name"
    assert item["authors"] == []
