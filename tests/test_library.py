"""音乐库的读写与体检。"""

from __future__ import annotations

import json

from app import paths
from app.core.library import Library
from app.models import Author, Tag, TagGroup


def test_missing_file_is_created(tmp_path):
    library = Library(tmp_path / "library.json")

    warnings = library.load()

    assert warnings == []
    assert library.path.exists()
    assert library.musics == {}


def test_roundtrip_keeps_records(tmp_path, music_factory):
    library = Library(tmp_path / "library.json")
    library.load()
    library.upsert_music(music_factory("a"))
    library.upsert_author(Author(uid="b" * 32, name="作者"))
    library.upsert_tag_group(TagGroup(uid="c" * 32, name="风格", tags=[Tag("d" * 32, "古典")]))
    library.save()

    reloaded = Library(library.path)
    reloaded.load()

    assert list(reloaded.musics) == ["a" * 32]
    assert reloaded.authors["b" * 32].name == "作者"
    assert reloaded.all_tags()["d" * 32].name == "古典"


def test_invalid_record_is_skipped_with_warning(tmp_path):
    path = tmp_path / "library.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "authors": [],
                "tag_groups": [],
                "musics": [
                    {"md5": "too-short", "names": ["坏记录"], "ext": "mp3"},
                    {"md5": "a" * 32, "names": ["好记录"], "ext": "mp3"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    library = Library(path)
    warnings = library.load()

    assert len(warnings) == 1
    assert list(library.musics) == ["a" * 32]


def test_duplicate_record_is_skipped(tmp_path):
    path = tmp_path / "library.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "authors": [],
                "tag_groups": [],
                "musics": [
                    {"md5": "a" * 32, "names": ["一"], "ext": "mp3"},
                    {"md5": "a" * 32, "names": ["二"], "ext": "mp3"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    library = Library(path)
    warnings = library.load()

    assert len(warnings) == 1
    assert library.musics["a" * 32].title == "一"


def test_counts_sum_duration_and_size(tmp_path, music_factory):
    library = Library(tmp_path / "library.json")
    library.load()
    library.upsert_music(music_factory("a", duration_ms=1000, size=10))
    library.upsert_music(music_factory("b", duration_ms=2000, size=20))

    counts = library.counts()

    assert counts["musics"] == 2
    assert counts["total_duration_ms"] == 3000
    assert counts["total_size"] == 30


def test_missing_files_uses_music_dir(tmp_path, music_factory, monkeypatch):
    monkeypatch.setattr(paths, "MUSIC_DIR", tmp_path / "music")
    library = Library(tmp_path / "library.json")
    library.load()
    library.upsert_music(music_factory("a"))

    assert library.missing_files() == ["a" * 32]

    paths.music_path("a" * 32, "mp3").parent.mkdir(parents=True)
    paths.music_path("a" * 32, "mp3").write_bytes(b"x")
    assert library.missing_files() == []


def test_tag_violations_only_for_compulsory_groups(tmp_path, music_factory):
    library = Library(tmp_path / "library.json")
    library.load()
    library.upsert_tag_group(
        TagGroup(uid="b" * 32, name="风格", compulsory=True, tags=[Tag("c" * 32, "古典")])
    )
    library.upsert_music(music_factory("a"))

    assert library.tag_violations() == ["a" * 32]

    library.musics["a" * 32].tags = ["c" * 32]
    assert library.tag_violations() == []


def test_broken_references_detects_unknown_author(tmp_path, music_factory):
    library = Library(tmp_path / "library.json")
    library.load()
    library.upsert_music(music_factory("a", authors=["f" * 32]))

    assert library.broken_references() == ["a" * 32]
