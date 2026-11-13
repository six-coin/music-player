"""启动恢复的六个分支。"""

from __future__ import annotations

from pathlib import Path

from app.core.library import Library
from app.core.player_session import Hooks, Load, PlayerSession, Stop
from app.core.playlists import PlaylistStore
from app.models import Music, Playlist

UID = "d" * 32


def md5(char: str) -> str:
    return char * 32


def build(tmp_path: Path, songs: str = "abc", hooks: Hooks | None = None) -> PlayerSession:
    library = Library(tmp_path / "library.json")
    for char in songs:
        library.musics[md5(char)] = Music(md5=md5(char), names=[f"Song {char}"], ext="mp3")
    store = PlaylistStore(tmp_path / "playlists.json")
    store.items[UID] = Playlist(
        uid=UID, name="测试", kind="manual", entries=[md5(char) for char in songs]
    )
    store.default_uid = UID
    return PlayerSession(library, store, mode="list_loop", hooks=hooks)


def test_restore_deleted_playlist_falls_back_to_empty(tmp_path):
    session = build(tmp_path)
    session.restore("f" * 32, None, 0)

    assert session.playlist_uid is None
    assert session.empty == "no_selection"
    assert session.current_md5 is None


def test_restore_track_not_in_playlist_stops_at_the_first(tmp_path):
    session = build(tmp_path)
    session.restore(UID, "e" * 32, 5000)

    assert session.current_md5 == md5("a")
    assert session.position_ms == 0
    assert session.playing is False
    assert session.command == Load(1, md5("a"), 0, False)


def test_restore_keeps_the_position(tmp_path):
    session = build(tmp_path)
    session.restore(UID, md5("b"), 42000)

    assert session.current_md5 == md5("b")
    assert session.position_ms == 42000
    assert session.command == Load(1, md5("b"), 42000, False)
    assert session.playing is False


def test_restore_skips_a_missing_file(tmp_path):
    session = build(tmp_path, hooks=Hooks(available=lambda item: item != md5("b")))
    session.restore(UID, md5("b"), 1000)

    assert session.current_md5 == md5("c")
    assert session.playing is False
    assert session.notice is not None and session.notice.kind == "missing"


def test_restore_empty_playlist_shows_the_empty_state(tmp_path):
    session = build(tmp_path, songs="")
    session.restore(UID, None, 0)

    assert session.empty == "empty_playlist"
    assert session.current_md5 is None
    assert isinstance(session.command, Stop)


def test_restore_without_a_playlist_is_no_selection(tmp_path):
    session = build(tmp_path)
    session.restore(None, None, 0)

    assert session.empty == "no_selection"
