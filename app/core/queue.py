"""一轮的播放顺序。

手动歌单保序，条件歌单按歌名；随机模式每轮重新洗牌，一轮内每首恰好一次。
只回答「一轮怎么排」，不记录播到哪——那是 ``player_session`` 的事。
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from app.core.library import Library
from app.core.playlists import PlaylistContent


def play_order(content: PlaylistContent, library: Library) -> list[str]:
    """列表循环的顺序：手动歌单按用户设定，条件歌单按歌名。"""

    def key(md5: str) -> tuple[str, str]:
        music = library.find_music(md5)
        return ((music.title if music else md5).casefold(), md5)

    if content.ordered:
        return list(content.md5s)
    return sorted(content.md5s, key=key)


def build_round(
    md5s: Sequence[str],
    mode: str,
    rng: random.Random,
    previous_last: str | None = None,
) -> list[str]:
    """生成一轮的顺序。

    随机模式每轮重新洗牌，一轮内每首恰好一次；其余模式按给定顺序。
    只处理轮与轮的接缝：新一轮首曲恰好是上一轮末曲时，把首曲与中间某首换开，
    否则听感上像「连着放了两遍」。
    """
    items = list(md5s)
    if mode != "shuffle":
        return items
    rng.shuffle(items)
    if len(items) > 1 and previous_last is not None and items[0] == previous_last:
        index = rng.randrange(1, len(items))
        items[0], items[index] = items[index], items[0]
    return items
