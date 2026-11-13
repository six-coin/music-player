"""一轮的顺序：洗牌、接缝与列表循环。"""

from __future__ import annotations

import random
from pathlib import Path

from app.core.library import Library
from app.core.playlists import PlaylistContent
from app.core.queue import build_round, play_order


def ids(count: int) -> list[str]:
    return [f"{index:032x}" for index in range(count)]


def test_shuffle_covers_every_song_exactly_once():
    items = ids(20)
    queue = build_round(items, "shuffle", random.Random(3))
    assert sorted(queue) == sorted(items)


def test_shuffle_never_repeats_across_the_seam():
    items = ids(20)
    rng = random.Random(11)
    first = build_round(items, "shuffle", rng)
    second = build_round(items, "shuffle", rng, first[-1])
    assert second[0] != first[-1]
    assert sorted(second) == sorted(items)


def test_shuffle_with_one_song_repeats_it():
    items = ids(1)
    assert build_round(items, "shuffle", random.Random(1), items[0]) == items


def test_list_loop_keeps_the_given_order():
    items = ids(5)
    assert build_round(items, "list_loop", random.Random(1)) == items


def test_play_order_keeps_manual_order(music_factory):
    library = Library(Path("library.json"))
    for char in "abc":
        library.musics[char * 32] = music_factory(char)
    content = PlaylistContent(["c" * 32, "a" * 32, "b" * 32], ordered=True)
    assert play_order(content, library) == ["c" * 32, "a" * 32, "b" * 32]


def test_play_order_sorts_filter_playlists_by_title(music_factory):
    library = Library(Path("library.json"))
    for char, title in (("a", "Charlie"), ("b", "alpha"), ("c", "Bravo")):
        library.musics[char * 32] = music_factory(char, names=[title])
    content = PlaylistContent(["a" * 32, "b" * 32, "c" * 32], ordered=False)
    assert play_order(content, library) == ["b" * 32, "c" * 32, "a" * 32]


def test_play_order_tolerates_unknown_songs():
    library = Library(Path("library.json"))
    content = PlaylistContent(["d" * 32], ordered=False)
    assert play_order(content, library) == ["d" * 32]
