"""完整性检查。"""

from __future__ import annotations

from pathlib import Path

from app import paths
from app.core import integrity
from app.core.importer import file_md5
from app.core.library import Library
from app.core.playlists import PlaylistStore
from app.core.stats import StatsStore
from app.models import Filter, Tag, TagGroup
from app.system import recycle


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


def test_playlist_reference_is_reported(tmp_path, music_factory):
    library = make_library(tmp_path)
    library.upsert_music(music_factory("a"))
    playlists = PlaylistStore(tmp_path / "playlists.json")
    playlists.load()
    playlist = playlists.create("手动", "manual")
    playlist.entries = ["a" * 32, "f" * 32]
    filtered = playlists.create("条件", "filter")
    filtered.filters = [Filter(mode="include", target="music", values=["f" * 32])]

    report = integrity.check(library, playlists)

    section = next(item for item in report["sections"] if item["key"] == "broken_reference")
    assert section["fixable"] is True
    assert any("手动" in item for item in section["items"])
    assert any("条件" in item for item in section["items"])


def test_stats_residue_is_reported_and_fixed(tmp_path, music_factory):
    library = make_library(tmp_path)
    library.upsert_music(music_factory("a"))
    playlists = PlaylistStore(tmp_path / "playlists.json")
    playlists.load()
    stats = StatsStore(tmp_path / "stats")
    playlist = playlists.default()
    stats.save(playlist.uid, {})
    stats.record(playlist.uid, "a" * 32, True, 100)
    stats.record(playlist.uid, "f" * 32, True, 100)

    report = integrity.check(library, playlists, stats)
    section = next(item for item in report["sections"] if item["key"] == "stats_residue")
    assert section["items"]

    fixed = integrity.fix(library, playlists, stats, "stats_residue")

    assert fixed["stats_residue"] == 1
    assert "f" * 32 not in stats.load(playlist.uid)
    assert "a" * 32 in stats.load(playlist.uid)


def test_broken_reference_can_be_fixed(tmp_path, music_factory):
    library = make_library(tmp_path)
    library.upsert_music(music_factory("a", authors=["f" * 32], tags=["e" * 32]))

    fixed = integrity.fix(library, None, None, "broken_reference")

    assert fixed["broken_reference"] == 1
    assert library.musics["a" * 32].authors == []
    assert library.musics["a" * 32].tags == []


def test_orphan_file_can_be_fixed(tmp_path, monkeypatch):
    paths.MUSIC_DIR.mkdir(parents=True)
    orphan = paths.MUSIC_DIR / ("f" * 32 + ".mp3")
    orphan.write_bytes(b"x")
    library = make_library(tmp_path)
    removed: list[Path] = []
    monkeypatch.setattr(recycle, "recycle", lambda path: (removed.append(Path(path)), True)[1])

    fixed = integrity.fix(library, None, None, "orphan_file")

    assert fixed["orphan_file"] == 1
    assert removed == [orphan]


def test_deep_check_detects_content_mismatch(tmp_path, music_factory):
    library = make_library(tmp_path)
    music = music_factory("a")
    library.upsert_music(music)
    paths.MUSIC_DIR.mkdir(parents=True)
    paths.music_path(music.md5, music.ext).write_bytes(b"not-the-same-content")

    report = integrity.deep_check(library)

    section = next(item for item in report["sections"] if item["key"] == "content_mismatch")
    assert "Song a" in section["items"][0]
    assert section["fixable"] is False


def test_deep_check_passes_for_matching_file(tmp_path, music_factory):
    library = make_library(tmp_path)
    paths.MUSIC_DIR.mkdir(parents=True)
    temp = tmp_path / "payload.bin"
    temp.write_bytes(b"payload")
    md5 = file_md5(temp)
    paths.music_path(md5, "mp3").write_bytes(b"payload")
    library.upsert_music(music_factory(md5=md5))

    report = integrity.deep_check(library)

    assert report["ok"] is True


def test_deep_check_reports_progress(tmp_path, music_factory, monkeypatch):
    monkeypatch.setattr(integrity.ffmpeg, "ffprobe_path", lambda: None)
    library = make_library(tmp_path)
    paths.MUSIC_DIR.mkdir(parents=True)
    temp = tmp_path / "payload.bin"
    temp.write_bytes(b"payload")
    md5 = file_md5(temp)
    paths.music_path(md5, "mp3").write_bytes(b"payload")
    library.upsert_music(music_factory(md5=md5))
    seen: list[tuple[int, int]] = []

    integrity.deep_check(library, progress=lambda done, total, name: seen.append((done, total)))

    assert seen[0] == (0, len(b"payload"))
    assert seen[-1][0] == seen[-1][1]


def test_deep_check_flags_declared_bitrate_that_does_not_match(
    tmp_path, music_factory, monkeypatch
):
    library = make_library(tmp_path)
    paths.MUSIC_DIR.mkdir(parents=True)
    music = music_factory("a")
    # 10 秒、约 12 KB：实际只有 10 kbps 左右，帧头却声明 320 kbps。
    paths.music_path(music.md5, music.ext).write_bytes(b"x" * 12000)
    library.upsert_music(music)
    monkeypatch.setattr(integrity.ffmpeg, "ffprobe_path", lambda: "ffprobe")
    monkeypatch.setattr(
        integrity.ffmpeg,
        "probe_stream",
        lambda path: {"bit_rate": 320000, "duration": 10.0, "size": 12000},
    )

    report = integrity.deep_check(library)

    section = next(item for item in report["sections"] if item["key"] == "fake_quality")
    assert section["fixable"] is False
    assert "码率虚标" in section["items"][0]
    assert "320 kbps" in section["items"][0]


def test_deep_check_accepts_honest_bitrate(tmp_path, music_factory, monkeypatch):
    library = make_library(tmp_path)
    paths.MUSIC_DIR.mkdir(parents=True)
    music = music_factory("a")
    paths.music_path(music.md5, music.ext).write_bytes(b"x" * 12000)
    library.upsert_music(music)
    monkeypatch.setattr(integrity.ffmpeg, "ffprobe_path", lambda: "ffprobe")
    monkeypatch.setattr(
        integrity.ffmpeg,
        "probe_stream",
        lambda path: {"bit_rate": 9600, "duration": 10.0, "size": 12000},
    )

    report = integrity.deep_check(library)

    assert "fake_quality" not in keys(report)
