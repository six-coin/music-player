"""完整性检查（快速档）。

只看记录与文件、引用与约束之间是否自洽，不重算 MD5。深检要遍历全部文件，
放在维护页单独触发。
"""

from __future__ import annotations

from typing import Any

from app import paths
from app.core.library import Library


def _missing_files(library: Library) -> list[str]:
    items: list[str] = []
    for md5 in library.missing_files():
        music = library.musics.get(md5)
        items.append(f"{music.title}（{md5}）" if music else md5)
    return items


def _orphan_files(library: Library) -> list[str]:
    if not paths.MUSIC_DIR.exists():
        return []
    items: list[str] = []
    for file in sorted(paths.MUSIC_DIR.iterdir()):
        if file.is_file() and file.suffix.lower() in (".mp3", ".m4a"):
            if file.stem not in library.musics:
                items.append(file.name)
    return items


def _broken_references(library: Library) -> list[str]:
    known_authors = set(library.authors)
    known_tags = set(library.all_tags())
    items: list[str] = []
    for music in library.musics.values():
        for uid in music.authors:
            if uid not in known_authors:
                items.append(f"{music.title}：作者 {uid}")
        for uid in music.tags:
            if uid not in known_tags:
                items.append(f"{music.title}：标签 {uid}")
    return items


def _tag_issues(library: Library) -> list[str]:
    items: list[str] = []
    for md5 in library.tag_violations():
        music = library.musics.get(md5)
        if music is None:
            continue
        selected = set(music.tags)
        missing = [
            group.name
            for group in library.tag_groups.values()
            if group.compulsory and not selected & {tag.uid for tag in group.tags}
        ]
        items.append(f"{music.title}：缺少 {'、'.join(missing)}")
    return items


def check(library: Library) -> dict[str, Any]:
    checks = (
        ("missing_file", _missing_files(library)),
        ("orphan_file", _orphan_files(library)),
        ("broken_reference", _broken_references(library)),
        ("tag_issue", _tag_issues(library)),
    )
    sections = [{"key": key, "items": items} for key, items in checks if items]
    return {
        "ok": not sections,
        "count": sum(len(section["items"]) for section in sections),
        "sections": sections,
    }
