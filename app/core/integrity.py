"""完整性检查与自动修复。

快速档只看记录与文件、引用与约束是否自洽；深检会把每个音频重算一遍 MD5，
按字节数报进度，允许中途取消。

报告里的 ``items`` 是给人看的字符串，修复动作不依赖它们——修复按类别重新扫一遍
现状再动手，这样即使用户在弹窗开着的时候改了库，也不会修错东西。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from loguru import logger

from app import paths
from app.core.importer import file_md5
from app.core.library import Library
from app.core.playlists import PlaylistStore
from app.core.stats import StatsStore
from app.system import recycle

FIXABLE = ("orphan_file", "broken_reference", "stats_residue")

Progress = Callable[[int, int, str], None]
Cancel = Callable[[], bool]


def _playlist_name(playlist) -> str:
    return playlist.name or "默认歌单"


# ---------- 各项检查 ----------


def _missing_files(library: Library) -> list[str]:
    items: list[str] = []
    for md5 in library.missing_files():
        music = library.musics.get(md5)
        items.append(f"{music.title}（{md5[:8]}）" if music else md5)
    return items


def orphan_paths(library: Library) -> list:
    """assets/music 里存在、但库里没有对应记录的文件。"""
    if not paths.MUSIC_DIR.exists():
        return []
    return [
        file
        for file in sorted(paths.MUSIC_DIR.iterdir())
        if file.is_file()
        and file.suffix.lower().lstrip(".") in ("mp3", "m4a")
        and file.stem not in library.musics
    ]


def _orphan_files(library: Library) -> list[str]:
    return [file.name for file in orphan_paths(library)]


def _broken_references(library: Library, playlists: PlaylistStore | None) -> list[str]:
    known_authors = set(library.authors)
    known_tags = set(library.all_tags())
    items: list[str] = []
    for music in library.musics.values():
        for uid in music.authors:
            if uid not in known_authors:
                items.append(f"{music.title}：作者 {uid[:8]} 不存在")
        for uid in music.tags:
            if uid not in known_tags:
                items.append(f"{music.title}：标签 {uid[:8]} 不存在")

    if playlists is None:
        return items

    known_musics = set(library.musics)
    known_playlists = set(playlists.items)
    for playlist in playlists.all():
        name = _playlist_name(playlist)
        if playlist.kind == "manual":
            missing = [md5 for md5 in playlist.entries if md5 not in known_musics]
            if missing:
                items.append(f"{name}：{len(missing)} 首歌已不在库里")
        for condition in playlist.filters:
            if condition.target == "music":
                missing = [value for value in condition.values if value not in known_musics]
                label = "歌曲"
            elif condition.target == "playlist":
                missing = [value for value in condition.values if value not in known_playlists]
                label = "歌单"
            elif condition.target == "tag":
                missing = [value for value in condition.values if value not in known_tags]
                label = "标签"
            elif condition.target == "author":
                missing = [value for value in condition.values if value not in known_authors]
                label = "作者"
            else:
                continue
            if missing:
                items.append(f"{name}：{len(missing)} 个{label}已不存在")
    return items


def _tag_issues(library: Library) -> list[str]:
    items: list[str] = []
    for md5 in library.tag_violations():
        music = library.musics.get(md5)
        if music is None:
            continue
        selected = set(music.tags)
        missing: list[str] = []
        conflicts: list[str] = []
        for group in library.tag_groups.values():
            chosen = selected & {tag.uid for tag in group.tags}
            if group.compulsory and not chosen:
                missing.append(group.name)
            if group.unique and len(chosen) > 1:
                conflicts.append(group.name)
        parts: list[str] = []
        if missing:
            parts.append(f"缺少 {'、'.join(missing)}")
        if conflicts:
            parts.append(f"{'、'.join(conflicts)} 只能选一个")
        items.append(f"{music.title}：{'；'.join(parts)}")
    return items


def _stats_residue(
    library: Library, playlists: PlaylistStore | None, stats: StatsStore | None
) -> list[str]:
    if playlists is None or stats is None or not stats.directory.exists():
        return []
    items: list[str] = []
    for file in sorted(stats.directory.glob("*.json")):
        uid = file.stem
        playlist = playlists.get(uid)
        if playlist is None:
            items.append(f"多余的统计文件：{file.name}")
            continue
        try:
            songs = stats.load(uid)
        except Exception as error:
            items.append(f"{_playlist_name(playlist)}：统计文件读不出来（{error}）")
            continue
        stale = [md5 for md5 in songs if md5 not in library.musics]
        if stale:
            items.append(f"{_playlist_name(playlist)}：{len(stale)} 条统计对应已删除的歌")
    return items


def _content_mismatch(
    library: Library, progress: Progress | None, cancel: Cancel | None
) -> list[str]:
    items: list[str] = []
    targets = []
    total = 0
    for music in library.musics.values():
        path = paths.music_path(music.md5, music.ext)
        try:
            size = path.stat().st_size
        except OSError:
            continue  # 文件不在或读不到：归「文件缺失」，不在这里重复报
        targets.append((music, path, size))
        total += size
    done = 0

    for music, path, size in targets:
        if cancel is not None and cancel():
            break
        if progress is not None:
            progress(done, total, music.title)
        try:
            actual = file_md5(path)
        except OSError as error:
            items.append(f"{music.title}：文件读不出来（{error}）")
            continue
        if actual != music.md5:
            items.append(f"{music.title}：文件内容与记录不符")
        done += size

    if progress is not None:
        progress(total, total, "")
    return items


# ---------- 汇总 ----------


def _report(sections: list[tuple[str, list[str]]]) -> dict[str, Any]:
    payload = [
        {"key": key, "fixable": key in FIXABLE, "items": items} for key, items in sections if items
    ]
    return {
        "ok": not payload,
        "count": sum(len(section["items"]) for section in payload),
        "sections": payload,
    }


def check(
    library: Library,
    playlists: PlaylistStore | None = None,
    stats: StatsStore | None = None,
) -> dict[str, Any]:
    """快速检查：不读音频内容。"""
    return _report(
        [
            ("missing_file", _missing_files(library)),
            ("orphan_file", _orphan_files(library)),
            ("broken_reference", _broken_references(library, playlists)),
            ("tag_issue", _tag_issues(library)),
            ("stats_residue", _stats_residue(library, playlists, stats)),
        ]
    )


def deep_check(
    library: Library,
    playlists: PlaylistStore | None = None,
    stats: StatsStore | None = None,
    progress: Progress | None = None,
    cancel: Cancel | None = None,
) -> dict[str, Any]:
    """在快速检查之上，把每个文件重算一遍 MD5。"""
    base = check(library, playlists, stats)
    mismatch = _content_mismatch(library, progress, cancel)
    if mismatch:
        base["sections"].append({"key": "content_mismatch", "fixable": False, "items": mismatch})
        base["ok"] = False
        base["count"] += len(mismatch)
    return base


# ---------- 修复 ----------


def _fix_references(library: Library, playlists: PlaylistStore | None) -> int:
    known_authors = set(library.authors)
    known_tags = set(library.all_tags())
    known_musics = set(library.musics)
    fixed = 0

    for music in library.musics.values():
        authors = [uid for uid in music.authors if uid in known_authors]
        tags = [uid for uid in music.tags if uid in known_tags]
        if authors != music.authors or tags != music.tags:
            music.authors = authors
            music.tags = tags
            fixed += 1

    if playlists is None:
        return fixed

    known_playlists = set(playlists.items)
    for playlist in playlists.all():
        touched = False
        if playlist.kind == "manual":
            entries = [md5 for md5 in playlist.entries if md5 in known_musics]
            if entries != playlist.entries:
                playlist.entries = entries
                touched = True
        for condition in playlist.filters:
            if condition.target == "music":
                allowed = known_musics
            elif condition.target == "playlist":
                allowed = known_playlists
            elif condition.target == "tag":
                allowed = known_tags
            elif condition.target == "author":
                allowed = known_authors
            else:
                continue
            values = [value for value in condition.values if value in allowed]
            if values != condition.values:
                condition.values = values
                touched = True
        if touched:
            fixed += 1
    return fixed


def _fix_stats(library: Library, playlists: PlaylistStore | None, stats: StatsStore | None) -> int:
    if playlists is None or stats is None or not stats.directory.exists():
        return 0
    fixed = 0
    for file in sorted(stats.directory.glob("*.json")):
        uid = file.stem
        if playlists.get(uid) is None:
            try:
                file.unlink()
                fixed += 1
            except OSError as error:
                logger.error("删除多余统计文件失败：{}", error)
            continue
        fixed += stats.prune(uid, set(library.musics))
    return fixed


def fix(
    library: Library,
    playlists: PlaylistStore | None,
    stats: StatsStore | None,
    kind: str = "",
) -> dict[str, int]:
    """修复可自动处理的问题；``kind`` 为空表示全部。"""
    counts: dict[str, int] = {}
    if kind in ("", "orphan_file"):
        files = orphan_paths(library)
        removed = sum(1 for file in files if recycle.recycle(file))
        counts["orphan_file"] = removed
    if kind in ("", "broken_reference"):
        counts["broken_reference"] = _fix_references(library, playlists)
    if kind in ("", "stats_residue"):
        counts["stats_residue"] = _fix_stats(library, playlists, stats)
    return counts
