"""模型的归一化与校验。"""

from __future__ import annotations

import pytest

from app.errors import DataError
from app.models import Adaptation, Author, Filter, Music, Playlist, Tag, TagGroup


def test_music_normalize_dedupes_and_strips():
    music = Music(
        md5="a" * 32,
        names=["  Experience  ", "Experience", "经验", ""],
        authors=["b" * 32, "b" * 32],
        tags=["c" * 32, "c" * 32, " "],
        ext=" MP3 ",
    )

    music.normalize()

    assert music.names == ["Experience", "经验"]
    assert music.authors == ["b" * 32]
    assert music.tags == ["c" * 32]
    assert music.ext == "mp3"
    assert music.title == "Experience"


def test_music_rejects_bad_values():
    with pytest.raises(DataError):
        Music(md5="short", names=["x"]).validate()

    with pytest.raises(DataError):
        Music(md5="a" * 32, names=[]).validate()

    with pytest.raises(DataError):
        Music(md5="a" * 32, names=["x"], ext="flac").validate()


def test_music_to_dict_has_only_contract_keys(music_factory):
    payload = music_factory().to_dict()

    assert set(payload) == {
        "md5",
        "names",
        "authors",
        "tags",
        "ext",
        "duration_ms",
        "size",
        "created_at",
        "updated_at",
    }


def test_author_and_tag_validation():
    author = Author(uid="a" * 32, name="  Ludovico  ", description="  ")
    author.normalize()
    author.validate()
    assert author.name == "Ludovico"
    assert author.description == ""

    with pytest.raises(DataError):
        Author(uid="a" * 32, name="").validate()

    with pytest.raises(DataError):
        Tag(uid="b" * 32, name=" ").validate()


def test_tag_group_detects_duplicate_tags():
    group = TagGroup(
        uid="a" * 32,
        name="风格",
        tags=[Tag(uid="b" * 32, name="古典"), Tag(uid="b" * 32, name="古典")],
    )
    group.normalize()

    with pytest.raises(DataError):
        group.validate()


def test_filter_all_drops_values():
    condition = Filter(mode="include", target="all", values=["a" * 32])
    condition.normalize()
    condition.validate()

    assert condition.values == []
    assert condition.to_dict() == {"mode": "include", "target": "all"}


def test_filter_allows_empty_values():
    """值可以先空着：界面允许先选对象类型再挑值，删歌也可能把值清空。"""
    condition = Filter(mode="include", target="tag", values=[])
    condition.normalize()

    condition.validate()

    assert condition.values == []


def test_playlist_builtin_forces_empty_name():
    playlist = Playlist(uid="a" * 32, name="随便起", builtin=True, kind="filter")
    playlist.filters = [Filter(mode="include", target="all")]

    playlist.normalize()

    assert playlist.name is None
    assert playlist.entries == []


def test_manual_playlist_drops_filters():
    playlist = Playlist(
        uid="a" * 32,
        name="深夜",
        kind="manual",
        entries=["b" * 32, "b" * 32],
        filters=[Filter()],
    )

    playlist.normalize()

    assert playlist.entries == ["b" * 32]
    assert playlist.filters == []


def test_playlist_requires_name_and_condition():
    with pytest.raises(DataError):
        Playlist(uid="a" * 32, name="  ", kind="manual").validate()

    with pytest.raises(DataError):
        Playlist(uid="a" * 32, name="空条件", kind="filter", filters=[]).validate()


def test_adaptation_clamps_and_keeps_none():
    adaptation = Adaptation(enabled=True, window=2, min_plays=999, base=1.5, skip_seconds=1)
    adaptation.normalize()

    assert adaptation.window == 10
    assert adaptation.min_plays == 10
    assert adaptation.base == 0.99
    assert adaptation.skip_seconds == 5

    untouched = Adaptation()
    untouched.normalize()
    assert untouched.window is None
    assert untouched.to_dict()["base"] is None
