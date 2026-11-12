"""导入流水线。"""

from __future__ import annotations

import shutil

import pytest

from app import paths
from app.core import importer
from app.core.library import Library


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "MUSIC_DIR", tmp_path / "music")
    monkeypatch.setattr(paths, "TEMP_DIR", tmp_path / "temp")


@pytest.fixture
def library(tmp_path):
    instance = Library(tmp_path / "library.json")
    instance.load()
    return instance


@pytest.fixture
def fake_ffmpeg(monkeypatch):
    monkeypatch.setattr(importer.ffmpeg, "available", lambda: True)
    monkeypatch.setattr(
        importer.ffmpeg,
        "clean_audio",
        lambda source, target, ext: shutil.copyfile(source, target),
    )
    monkeypatch.setattr(importer.ffmpeg, "probe_duration_ms", lambda path: 1234)


def test_import_creates_record_and_file(tmp_path, library, fake_ffmpeg):
    source = tmp_path / "Song A - Alice, Bob.mp3"
    source.write_bytes(b"audio-bytes")

    outcome = importer.import_file(source, library, clean=True)

    assert outcome.error == ""
    assert outcome.music is not None
    assert outcome.music.title == "Song A"
    assert outcome.music.duration_ms == 1234
    assert [author.name for author in library.authors.values()] == ["Alice", "Bob"]
    assert paths.music_path(outcome.music.md5, "mp3").exists()
    assert source.exists()


def test_second_import_is_duplicate(tmp_path, library, fake_ffmpeg):
    source = tmp_path / "Song.mp3"
    source.write_bytes(b"audio-bytes")

    importer.import_file(source, library, clean=True)
    second = importer.import_file(source, library, clean=True)

    assert second.duplicate is True
    assert second.music is None


def test_unsupported_extension_is_rejected(tmp_path, library, fake_ffmpeg):
    source = tmp_path / "Song.flac"
    source.write_bytes(b"audio-bytes")

    outcome = importer.import_file(source, library, clean=True)

    assert "不支持" in outcome.error


def test_missing_file_is_reported(tmp_path, library, fake_ffmpeg):
    outcome = importer.import_file(tmp_path / "nope.mp3", library, clean=True)

    assert "不存在" in outcome.error


def test_clean_requires_ffmpeg(tmp_path, library, monkeypatch):
    monkeypatch.setattr(importer.ffmpeg, "available", lambda: False)
    source = tmp_path / "Song.mp3"
    source.write_bytes(b"audio-bytes")

    outcome = importer.import_file(source, library, clean=True)

    assert "FFmpeg" in outcome.error


def test_existing_target_is_adopted(tmp_path, library, monkeypatch):
    monkeypatch.setattr(importer.ffmpeg, "available", lambda: False)
    source = tmp_path / "Song.mp3"
    source.write_bytes(b"audio-bytes")
    md5 = importer.file_md5(source)
    target = paths.music_path(md5, "mp3")
    target.parent.mkdir(parents=True)
    target.write_bytes(b"audio-bytes")
    monkeypatch.setattr(importer.ffmpeg, "probe_duration_ms", lambda path: 0)

    outcome = importer.import_file(source, library, clean=False)

    assert outcome.error == ""
    assert outcome.music is not None
    assert outcome.music.md5 == md5
