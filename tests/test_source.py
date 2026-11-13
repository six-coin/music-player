"""换源与删除：引用迁移、统计搬家、回收站。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import paths
from app.core import source
from app.core.adaptation import Params
from app.core.importer import file_md5
from app.core.library import Library
from app.core.playlists import PlaylistStore
from app.core.stats import StatsStore
from app.errors import ActionError
from app.models import Filter, Music
from app.system import recycle

PARAMS = Params(window=100, min_plays=10, base=0.95, skip_seconds=30)


@pytest.fixture(autouse=True)
def quiet_recycle(monkeypatch):
    """测试不往真实回收站里丢文件。"""

    def fake(path, name):
        Path(path).unlink(missing_ok=True)
        return True

    monkeypatch.setattr(recycle, "recycle_as", fake)


def make_music(md5: str, name: str = "Song") -> Music:
    return Music(md5=md5, names=[name], ext="mp3", duration_ms=1000, size=10)


def seed(tmp_path):
    library = Library(tmp_path / "library.json")
    library.load()
    playlists = PlaylistStore(tmp_path / "playlists.json")
    playlists.load()
    stats = StatsStore(tmp_path / "stats")
    return library, playlists, stats


def test_replace_source_migrates_library_playlists_and_stats(tmp_path):
    library, playlists, stats = seed(tmp_path)
    paths.MUSIC_DIR.mkdir(parents=True, exist_ok=True)

    old_file = paths.music_path("a" * 32, "mp3")
    old_file.write_bytes(b"old-audio")
    music = make_music("a" * 32, "夜曲")
    library.upsert_music(music)

    manual = playlists.create("手动", "manual")
    manual.entries = ["a" * 32]
    filtered = playlists.create("条件", "filter")
    filtered.filters = [Filter(mode="include", target="music", values=["a" * 32])]
    playlists.save()
    stats.record(manual.uid, "a" * 32, True, 100)

    new_file = tmp_path / "new.mp3"
    new_file.write_bytes(b"new-audio-bytes")
    prepared = source.prepare_replacement(new_file, clean=False)

    report = source.apply_replacement(music, prepared, library, playlists, stats, PARAMS)

    assert report.new_md5 == file_md5(new_file)
    assert report.playlists == 2
    assert report.stats == 1
    assert report.new_md5 in library.musics
    assert "a" * 32 not in library.musics
    assert library.musics[report.new_md5].names == ["夜曲"]
    assert paths.music_path(report.new_md5, "mp3").exists()
    assert not old_file.exists()
    assert playlists.get(manual.uid).entries == [report.new_md5]
    assert playlists.get(filtered.uid).filters[0].values == [report.new_md5]
    assert report.new_md5 in stats.load(manual.uid)
    assert "a" * 32 not in stats.load(manual.uid)


def test_replace_source_rejects_identical_content(tmp_path):
    library, playlists, stats = seed(tmp_path)
    paths.MUSIC_DIR.mkdir(parents=True, exist_ok=True)

    audio = tmp_path / "same.mp3"
    audio.write_bytes(b"identical")
    md5 = file_md5(audio)
    paths.music_path(md5, "mp3").write_bytes(audio.read_bytes())
    music = make_music(md5)
    library.upsert_music(music)

    prepared = source.prepare_replacement(audio, clean=False)

    with pytest.raises(ActionError, match="无需更换"):
        source.apply_replacement(music, prepared, library, playlists, stats, PARAMS)


def test_replace_source_rejects_conflict(tmp_path):
    library, playlists, stats = seed(tmp_path)
    paths.MUSIC_DIR.mkdir(parents=True, exist_ok=True)

    audio = tmp_path / "new.mp3"
    audio.write_bytes(b"conflict-bytes")
    new_md5 = file_md5(audio)

    old = make_music("a" * 32, "旧歌")
    library.upsert_music(old)
    library.upsert_music(make_music(new_md5, "已经存在的歌"))

    prepared = source.prepare_replacement(audio, clean=False)

    with pytest.raises(ActionError, match="已经存在的歌"):
        source.apply_replacement(old, prepared, library, playlists, stats, PARAMS)
    assert "a" * 32 in library.musics


def test_delete_music_removes_every_reference(tmp_path):
    library, playlists, stats = seed(tmp_path)
    paths.MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    paths.music_path("a" * 32, "mp3").write_bytes(b"a")
    paths.music_path("b" * 32, "mp3").write_bytes(b"b")

    library.upsert_music(make_music("a" * 32, "要走"))
    library.upsert_music(make_music("b" * 32, "留下"))
    manual = playlists.create("手动", "manual")
    manual.entries = ["a" * 32, "b" * 32]
    filtered = playlists.create("条件", "filter")
    filtered.filters = [Filter(mode="include", target="music", values=["a" * 32])]
    playlists.save()
    stats.record(manual.uid, "a" * 32, False, 100)
    stats.record(manual.uid, "b" * 32, True, 100)

    report = source.delete_musics(["a" * 32], library, playlists, stats)

    assert report.removed == 1
    assert "a" * 32 not in library.musics
    assert playlists.get(manual.uid).entries == ["b" * 32]
    assert playlists.get(filtered.uid).filters[0].values == []
    assert "a" * 32 not in stats.load(manual.uid)
    assert "b" * 32 in stats.load(manual.uid)
    assert not paths.music_path("a" * 32, "mp3").exists()


def test_delete_unknown_music_is_noop(tmp_path):
    library, playlists, stats = seed(tmp_path)

    report = source.delete_musics(["f" * 32], library, playlists, stats)

    assert report.removed == 0
    assert library.musics == {}
