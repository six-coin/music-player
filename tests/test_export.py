"""导出：文件名规则与「复制原文件」的行为。"""

from __future__ import annotations

import json
from pathlib import Path

from app import paths
from app.core.naming import export_filename
from app.ui.manager.api import ManagerApi

UID = "d" * 32
AUTHOR_A = "1" * 32
AUTHOR_B = "2" * 32
MD5 = "a" * 32


def write_config(root: Path) -> None:
    library = {
        "version": 1,
        "authors": [
            {"uid": AUTHOR_A, "name": "Owl City"},
            {"uid": AUTHOR_B, "name": "Carly Rae Jepsen"},
        ],
        "tag_groups": [],
        "musics": [
            {
                "md5": MD5,
                "names": ["Good Time"],
                "authors": [AUTHOR_A, AUTHOR_B],
                "tags": [],
                "ext": "mp3",
                "duration_ms": 1000,
            }
        ],
    }
    playlists = {"version": 1, "default_uid": UID, "items": []}
    (root / "library.json").write_text(json.dumps(library), encoding="utf-8")
    (root / "playlists.json").write_text(json.dumps(playlists), encoding="utf-8")
    music = paths.music_path(MD5, "mp3")
    music.parent.mkdir(parents=True, exist_ok=True)
    music.write_bytes(b"original-bytes")


def test_export_filename_keeps_the_original_format():
    assert (
        export_filename("Good Time", ["Owl City", "Carly Rae Jepsen"], "mp3")
        == "Good Time - Owl City, Carly Rae Jepsen.mp3"
    )
    # 没有作者时不留一个空的分隔符。
    assert export_filename("Solo", [], "ogg") == "Solo.ogg"


def test_export_filename_drops_characters_windows_rejects():
    assert export_filename("AC/DC: Back?", ["A|B"], "flac") == "ACDC Back - AB.flac"
    assert export_filename("  trailing...  ", [], "mp3") == "trailing.mp3"
    assert export_filename("   ", [], "mp3") == "未命名.mp3"
    # 保留设备名带不带后缀都不能用。
    assert export_filename("CON", [], "ogg") == "_CON.ogg"


def test_export_copies_the_file_and_never_overwrites(tmp_path):
    write_config(tmp_path)
    target = tmp_path / "out"
    target.mkdir()
    api = ManagerApi(config_dir=tmp_path)
    api._ask_export_dir = lambda: target
    try:
        first = api.export_musics([MD5])
        assert first["ok"] is True
        assert first["exported"] == 1
        exported = target / "Good Time - Owl City, Carly Rae Jepsen.mp3"
        assert exported.read_bytes() == b"original-bytes"

        second = api.export_musics([MD5])
        assert second["exported"] == 1
        assert (target / "Good Time - Owl City, Carly Rae Jepsen (2).mp3").exists()
        assert exported.read_bytes() == b"original-bytes"
    finally:
        api.close()


def test_export_reports_missing_files(tmp_path):
    write_config(tmp_path)
    paths.music_path(MD5, "mp3").unlink()
    target = tmp_path / "out"
    target.mkdir()
    api = ManagerApi(config_dir=tmp_path)
    api._ask_export_dir = lambda: target
    try:
        result = api.export_musics([MD5])
        assert result["ok"] is True
        assert result["exported"] == 0
        assert result["errors"]
        assert list(target.iterdir()) == []
    finally:
        api.close()


def test_export_cancel_returns_nothing(tmp_path):
    write_config(tmp_path)
    api = ManagerApi(config_dir=tmp_path)
    api._ask_export_dir = lambda: None
    try:
        assert api.export_musics([MD5])["canceled"] is True
        assert api.export_musics([])["canceled"] is True
    finally:
        api.close()
