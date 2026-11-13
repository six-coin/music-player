"""player 状态机：模式、轮次、队列、pin、自适应与缺失。"""

from __future__ import annotations

import random
from pathlib import Path

from app.core.library import Library
from app.core.player_session import Hooks, Load, PlayerSession, Stop
from app.core.playlists import PlaylistStore
from app.models import Music, Playlist

UID = "d" * 32


def md5(char: str) -> str:
    return char * 32


def build(
    tmp_path: Path,
    songs: str = "abc",
    mode: str = "list_loop",
    hooks: Hooks | None = None,
    seed: int = 7,
) -> tuple[PlayerSession, Library, PlaylistStore]:
    library = Library(tmp_path / "library.json")
    for char in songs:
        library.musics[md5(char)] = Music(
            md5=md5(char), names=[f"Song {char}"], ext="mp3", duration_ms=1000
        )
    store = PlaylistStore(tmp_path / "playlists.json")
    store.items[UID] = Playlist(
        uid=UID, name="测试", kind="manual", entries=[md5(char) for char in songs]
    )
    store.default_uid = UID
    session = PlayerSession(library, store, mode=mode, rng=random.Random(seed), hooks=hooks)
    return session, library, store


def test_load_playlist_starts_first_and_autoplays(tmp_path):
    session, _, _ = build(tmp_path)
    session.load_playlist(UID, autoplay=True)

    assert session.current_md5 == md5("a")
    assert session.playing is True
    assert session.command == Load(1, md5("a"), 0, True)
    assert session.empty is None


def test_queue_follows_the_round(tmp_path):
    session, _, _ = build(tmp_path)
    session.load_playlist(UID, autoplay=True)

    assert session.queue() == ([md5("b"), md5("c")], 0)

    session.next()
    assert session.queue() == ([md5("c")], 0)


def test_last_track_still_shows_next_round(tmp_path):
    session, _, _ = build(tmp_path)
    session.load_playlist(UID, autoplay=True)
    session.next()
    session.next()

    items, _ = session.queue()
    assert items == [md5("a"), md5("b"), md5("c")]  # 列表循环的下一轮就是本轮


def test_last_track_of_a_shuffle_round_shows_the_next_round(tmp_path):
    session, _, _ = build(tmp_path, mode="shuffle", seed=3)
    session.load_playlist(UID, autoplay=True)
    session.next()
    session.next()

    items, _ = session.queue()
    assert len(items) == 3
    assert items[0] != session.current_md5  # 新一轮首曲避开上一轮末曲


def test_list_loop_wraps_at_the_end(tmp_path):
    session, _, _ = build(tmp_path)
    session.load_playlist(UID, autoplay=True)
    session.next()
    session.next()
    session.next()

    assert session.current_md5 == md5("a")


def test_previous_is_disabled_at_the_first_track(tmp_path):
    session, _, _ = build(tmp_path)
    session.load_playlist(UID, autoplay=True)

    assert session.can_prev() is False
    session.next()
    assert session.can_prev() is True
    assert session.previous() is True
    assert session.current_md5 == md5("a")


def test_repeat_one_replays_the_same_track(tmp_path):
    session, _, _ = build(tmp_path, mode="repeat_one")
    session.load_playlist(UID, autoplay=True)
    first = session.command

    assert session.on_ended() is True
    assert session.current_md5 == md5("a")
    assert session.command.seq == first.seq + 1
    assert session.command.position_ms == 0
    assert session.command.autoplay is True


def test_repeat_one_queue_shows_the_whole_playlist(tmp_path):
    session, _, _ = build(tmp_path, mode="repeat_one")
    session.load_playlist(UID, autoplay=True)

    items, _ = session.queue()
    assert items == [md5("a"), md5("b"), md5("c")]
    assert session.snapshot()["current_md5"] == md5("a")


def test_shuffle_round_covers_every_song_once(tmp_path):
    session, _, _ = build(tmp_path, songs="abcdefgh", mode="shuffle", seed=11)
    session.load_playlist(UID, autoplay=True)

    played = [session.current_md5]
    for _ in range(7):
        session.next()
        played.append(session.current_md5)
    assert sorted(played) == sorted(md5(char) for char in "abcdefgh")


def test_shuffle_seam_avoids_the_previous_last(tmp_path):
    session, _, _ = build(tmp_path, songs="abcdefgh", mode="shuffle", seed=5)
    session.load_playlist(UID, autoplay=True)
    for _ in range(7):
        session.next()
    last = session.current_md5

    session.next()
    assert session.current_md5 != last


def test_auto_skip_leaves_the_queue(tmp_path):
    skipped: list[str] = []
    hooks = Hooks(
        should_skip=lambda _uid, item: item == md5("b"),
        on_auto_skip=lambda uid, item: skipped.append(item),
    )
    session, _, _ = build(tmp_path, hooks=hooks)
    session.load_playlist(UID, autoplay=True)
    assert md5("b") in session.queue()[0]

    session.next()

    assert session.current_md5 == md5("c")
    assert md5("b") not in session.queue()[0]
    assert skipped == [md5("b")]


def test_all_skipped_stops_without_looping(tmp_path):
    hooks = Hooks(should_skip=lambda _uid, _item: True)
    session, _, _ = build(tmp_path, hooks=hooks)
    session.load_playlist(UID, autoplay=True)

    assert session.next() is False
    assert session.current_md5 is None
    assert session.empty == "unplayable"
    assert isinstance(session.command, Stop)
    assert session.notice is not None and session.notice.kind == "all_skipped"


def test_missing_track_is_skipped_but_stays_in_the_queue(tmp_path):
    hooks = Hooks(available=lambda item: item != md5("b"))
    session, _, _ = build(tmp_path, hooks=hooks)
    session.load_playlist(UID, autoplay=True)

    assert md5("b") in session.queue()[0]
    session.next()
    assert session.current_md5 == md5("c")
    assert session.notice is not None and session.notice.kind == "missing"


def test_pin_only_for_songs_outside_the_playlist(tmp_path):
    session, library, _ = build(tmp_path)
    library.musics[md5("e")] = Music(md5=md5("e"), names=["Outside"], ext="mp3")
    session.load_playlist(UID, autoplay=True)

    assert session.pick_loop_song(md5("b")) is True
    assert session.pin is None
    assert session.mode == "repeat_one"
    assert session.current_md5 == md5("b")

    assert session.pick_loop_song(md5("e")) is True
    assert session.pin is not None
    assert session.current_md5 == md5("e")
    assert session.queue() == ([], 0)


def test_exit_repeat_one_restores_the_origin(tmp_path):
    session, library, _ = build(tmp_path)
    library.musics[md5("e")] = Music(md5=md5("e"), names=["Outside"], ext="mp3")
    session.load_playlist(UID, autoplay=True)
    session.next()  # 停在 b
    session.set_position(42000)
    session.pick_loop_song(md5("e"))

    assert session.set_mode("list_loop") is True
    assert session.current_md5 == md5("b")
    assert session.pin is None
    assert session.command.position_ms == 42000
    assert session.command.autoplay is True


def test_next_clears_the_pin_and_moves_from_the_origin(tmp_path):
    session, library, _ = build(tmp_path)
    library.musics[md5("e")] = Music(md5=md5("e"), names=["Outside"], ext="mp3")
    session.load_playlist(UID, autoplay=True)
    session.pick_loop_song(md5("e"))

    session.next()

    assert session.pin is None
    assert session.current_md5 == md5("b")


def test_jump_can_go_back_within_the_round(tmp_path):
    session, _, _ = build(tmp_path)
    session.load_playlist(UID, autoplay=True)
    session.next()
    session.next()

    assert session.jump(md5("a")) is True
    assert session.current_md5 == md5("a")
    assert session.command.autoplay is True
