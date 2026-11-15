"""换源与删除。

换源是「同一首歌换一个音频文件」：名称、作者、标签、歌单归属、统计都留在原地，
只有身份（MD5）与文件本身被替换。删除则要把这首歌从库、歌单、统计三处一起摘掉，
音频送进回收站。

两个操作都要动三份文件，任何一步失败都必须回到「旧状态仍然可用」，所以先备份
内存状态，失败时写回。
"""

from __future__ import annotations

import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from app import paths
from app.core.adaptation import Params, effective
from app.core.importer import file_md5
from app.core.library import Library
from app.core.naming import sanitize_filename
from app.core.playlists import PlaylistStore
from app.core.stats import StatsStore
from app.core.totals import TotalStore
from app.errors import ActionError
from app.models import AUDIO_EXTS, Music
from app.system import ffmpeg, recycle


@dataclass(slots=True)
class Prepared:
    """待替换的音频已经落到临时目录，身份也算好了。"""

    temp: Path
    md5: str
    ext: str
    size: int
    duration_ms: int


@dataclass(slots=True)
class ReplaceReport:
    title: str = ""
    old_md5: str = ""
    new_md5: str = ""
    playlists: int = 0
    stats: int = 0
    recycled: bool = True


@dataclass(slots=True)
class DeleteReport:
    removed: int = 0
    playlists: int = 0
    stats: int = 0
    recycled: int = 0


def prepare_replacement(source: Path, clean: bool) -> Prepared:
    """把新文件清洗/复制到临时目录，算出新 MD5；失败时不留临时文件。"""
    path = Path(source)
    try:
        path = path.resolve()
    except OSError as error:
        raise ActionError(f"文件路径无法解析：{error}") from error
    if not path.is_file():
        raise ActionError("文件不存在")

    ext = path.suffix.lower().lstrip(".")
    if ext not in AUDIO_EXTS:
        raise ActionError(f"不支持的格式：.{ext}")

    paths.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    temp = paths.TEMP_DIR / f"source_{uuid.uuid4().hex}.{ext}"
    if clean:
        if not ffmpeg.available():
            raise ActionError("未检测到 FFmpeg，请先安装并加入 PATH，或在设置里关闭音频清洗")
        try:
            ffmpeg.clean_audio(path, temp, ext)
        except Exception as error:
            temp.unlink(missing_ok=True)
            raise ActionError(f"音频清洗失败：{error}") from error
    else:
        try:
            shutil.copy2(path, temp)
        except OSError as error:
            temp.unlink(missing_ok=True)
            raise ActionError(f"复制文件失败：{error}") from error

    try:
        return Prepared(
            temp=temp,
            md5=file_md5(temp),
            ext=ext,
            size=temp.stat().st_size,
            duration_ms=ffmpeg.probe_duration_ms(temp),
        )
    except OSError as error:
        temp.unlink(missing_ok=True)
        raise ActionError(f"读取文件失败：{error}") from error


def apply_replacement(
    music: Music,
    prepared: Prepared,
    library: Library,
    playlists: PlaylistStore,
    stats: StatsStore,
    defaults: Params,
    totals: TotalStore | None = None,
) -> ReplaceReport:
    old_md5 = music.md5
    old_ext = music.ext
    title = music.title

    if prepared.md5 == old_md5:
        prepared.temp.unlink(missing_ok=True)
        raise ActionError("新文件与当前源文件内容一致，无需更换")

    conflict = library.musics.get(prepared.md5)
    if conflict is not None:
        prepared.temp.unlink(missing_ok=True)
        raise ActionError(f"这个文件已经是库里的《{conflict.title}》，没有替换")

    target = paths.music_path(prepared.md5, prepared.ext)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(prepared.temp), str(target))
    except OSError as error:
        prepared.temp.unlink(missing_ok=True)
        raise ActionError(f"写入新文件失败：{error}") from error

    library_backup = library.to_payload()
    playlist_backup = playlists.to_payload()

    try:
        del library.musics[old_md5]
        music.md5 = prepared.md5
        music.ext = prepared.ext
        music.size = prepared.size
        music.duration_ms = prepared.duration_ms
        music.updated_at = int(time.time())
        library.musics[prepared.md5] = music

        changed = playlists.replace_song(old_md5, prepared.md5)
        library.save()
        playlists.save()
    except Exception as error:
        library.restore(library_backup)
        playlists.restore(playlist_backup)
        try:
            library.save()
            playlists.save()
        except Exception:  # 回滚也失败就只能记日志了
            logger.exception("换源回滚失败")
        target.unlink(missing_ok=True)
        raise ActionError(f"迁移引用失败：{error}") from error

    stats_changed = 0
    for playlist in playlists.all():
        window = effective(playlist.adaptation, defaults).window
        try:
            if stats.move_key(playlist.uid, old_md5, prepared.md5, window):
                stats_changed += 1
        except Exception:  # 统计不是关键数据，失败不阻断换源
            logger.exception("迁移统计失败：{}", playlist.uid)

    if totals is not None:
        try:
            totals.move_key(old_md5, prepared.md5)
        except Exception:  # 同上：总播放次数也是附加物
            logger.exception("迁移总播放次数失败：{}", old_md5)

    old_path = paths.music_path(old_md5, old_ext)
    recycled = recycle.recycle_as(old_path, f"{sanitize_filename(title)}（旧源）")

    return ReplaceReport(
        title=title,
        old_md5=old_md5,
        new_md5=prepared.md5,
        playlists=changed,
        stats=stats_changed,
        recycled=recycled,
    )


def delete_musics(
    md5s: list[str],
    library: Library,
    playlists: PlaylistStore,
    stats: StatsStore,
    totals: TotalStore | None = None,
) -> DeleteReport:
    report = DeleteReport()
    library_backup = library.to_payload()
    playlist_backup = playlists.to_payload()
    changed_playlists: set[str] = set()

    try:
        for md5 in md5s:
            music = library.musics.pop(md5, None)
            if music is None:
                continue
            report.removed += 1
            changed_playlists.update(playlists.drop_song(md5))
            for playlist in playlists.all():
                if stats.drop(playlist.uid, md5):
                    report.stats += 1
            if totals is not None:
                totals.drop(md5)
            if recycle.recycle_as(paths.music_path(md5, music.ext), sanitize_filename(music.title)):
                report.recycled += 1
        library.save()
        playlists.save()
    except Exception as error:
        library.restore(library_backup)
        playlists.restore(playlist_backup)
        try:
            library.save()
            playlists.save()
        except Exception:
            logger.exception("删除回滚失败")
        raise ActionError(f"删除失败：{error}") from error

    report.playlists = len(changed_playlists)
    return report
