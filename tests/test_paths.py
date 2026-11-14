"""路径解析。"""

from __future__ import annotations

from app import paths


def test_empty_text_falls_back_to_program_dir():
    assert paths.resolve_user_path("") == paths.PROGRAM_DIR
    assert paths.resolve_user_path("   ") == paths.PROGRAM_DIR


def test_relative_path_is_based_on_the_data_dir():
    resolved = paths.resolve_user_path("music")
    assert resolved == (paths.DATA_DIR / "music").resolve()


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


def test_data_dir_pointer_round_trips(tmp_path, monkeypatch):
    """指针写在本地目录，读回来就是新数据目录。"""
    monkeypatch.delenv("SIXCOIN_DATA_DIR", raising=False)
    monkeypatch.setattr(paths, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(paths, "DATA_POINTER", tmp_path / "data-dir.txt")
    target = tmp_path / "custom-data"

    paths.write_data_dir(target)

    assert paths.read_data_dir() == target


def test_migration_moves_config_and_drops_locks(tmp_path, monkeypatch):
    """旧 config 搬进数据目录，旧锁文件直接丢掉。"""
    program = tmp_path / "program"
    (program / "config").mkdir(parents=True)
    (program / "config" / "app.json").write_text("{}", encoding="utf-8")
    (program / "config" / "stale.lock").write_text("", encoding="utf-8")
    data = tmp_path / "data"
    monkeypatch.setattr(paths, "PROGRAM_DIR", program)
    monkeypatch.setattr(paths, "DATA_DIR", data)
    monkeypatch.setattr(paths, "LOG_DIR", tmp_path / "logs")

    paths.migrate_legacy()

    assert (data / "app.json").is_file()
    assert not (data / "stale.lock").exists()
