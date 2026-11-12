"""完整性检查。"""

from __future__ import annotations

from app import paths
from app.core import integrity
from app.core.library import Library
from app.models import Tag, TagGroup


def make_library(tmp_path) -> Library:
    library = Library(tmp_path / "library.json")
    library.load()
    return library


def keys(report) -> list[str]:
    return [section["key"] for section in report["sections"]]


def test_clean_library_has_no_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "MUSIC_DIR", tmp_path / "music")
    library = make_library(tmp_path)

    report = integrity.check(library)

    assert report["ok"] is True
    assert report["count"] == 0
    assert report["sections"] == []


def test_missing_file_is_reported(tmp_path, music_factory, monkeypatch):
    monkeypatch.setattr(paths, "MUSIC_DIR", tmp_path / "music")
    library = make_library(tmp_path)
    library.upsert_music(music_factory("a"))

    report = integrity.check(library)

    assert keys(report) == ["missing_file"]
    assert report["sections"][0]["items"][0].startswith("Song a")


def test_orphan_file_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "MUSIC_DIR", tmp_path / "music")
    paths.MUSIC_DIR.mkdir(parents=True)
    (paths.MUSIC_DIR / ("f" * 32 + ".mp3")).write_bytes(b"x")
    library = make_library(tmp_path)

    report = integrity.check(library)

    assert keys(report) == ["orphan_file"]


def test_broken_reference_is_reported(tmp_path, music_factory, monkeypatch):
    monkeypatch.setattr(paths, "MUSIC_DIR", tmp_path / "music")
    library = make_library(tmp_path)
    library.upsert_music(music_factory("a", authors=["f" * 32]))

    report = integrity.check(library)

    assert "broken_reference" in keys(report)


def test_tag_violation_is_reported(tmp_path, music_factory, monkeypatch):
    monkeypatch.setattr(paths, "MUSIC_DIR", tmp_path / "music")
    library = make_library(tmp_path)
    library.upsert_tag_group(
        TagGroup(uid="b" * 32, name="风格", compulsory=True, tags=[Tag("c" * 32, "古典")])
    )
    library.upsert_music(music_factory("a"))

    report = integrity.check(library)

    assert "tag_issue" in keys(report)
    assert "风格" in report["sections"][-1]["items"][0]
