"""路径解析。"""

from __future__ import annotations

from app import paths


def test_empty_text_falls_back_to_program_dir():
    assert paths.resolve_user_path("") == paths.PROGRAM_DIR
    assert paths.resolve_user_path("   ") == paths.PROGRAM_DIR


def test_relative_path_is_based_on_program_dir():
    resolved = paths.resolve_user_path("assets/music")
    assert resolved == (paths.PROGRAM_DIR / "assets" / "music").resolve()


def test_absolute_path_is_kept(tmp_path):
    assert paths.resolve_user_path(str(tmp_path)) == tmp_path


def test_quotes_are_stripped(tmp_path):
    assert paths.resolve_user_path(f'"{tmp_path}"') == tmp_path


def test_forward_slashes_are_accepted(tmp_path):
    raw = str(tmp_path).replace("\\", "/")
    assert paths.resolve_user_path(raw) == tmp_path


def test_music_path_uses_md5_and_ext():
    path = paths.music_path("a" * 32, "m4a")
    assert path.name == f"{'a' * 32}.m4a"
    assert path.parent == paths.MUSIC_DIR


def test_stats_path_is_per_playlist():
    path = paths.stats_path("b" * 32)
    assert path.name == f"{'b' * 32}.json"
    assert path.parent == paths.STATS_DIR
