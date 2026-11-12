"""导入流水线。

选择文件 → 校验后缀 → 清洗（可选） → 计算 MD5 → 落盘 → 写库。
清洗后的字节决定身份，所以同一个文件在不同机器上导入应当得到同一个 MD5。
"""

from __future__ import annotations

import hashlib
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from app import paths
from app.core.library import Library
from app.core.naming import parse_filename
from app.errors import ActionError
from app.models import AUDIO_EXTS, Author, Music, new_uid
from app.system import ffmpeg


@dataclass(slots=True)
class ImportOutcome:
    music: Music | None = None
    duplicate: bool = False
    error: str = ""


def file_md5(path: Path) -> str:
    hasher = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def ensure_author(library: Library, name: str) -> str:
    """按名称复用作者，没有就建一个。"""
    for author in library.authors.values():
        if author.name == name:
            return author.uid
    author = Author(uid=new_uid(), name=name)
    library.upsert_author(author)
    return author.uid


def _prepare(source: Path, ext: str, clean: bool) -> tuple[Path, str]:
    """返回（待入库的文件, MD5）。清洗产物在临时目录，调用方负责清理。"""
    if not clean:
        return source, file_md5(source)

    if not ffmpeg.available():
        raise ActionError("未检测到 FFmpeg，请先安装并加入 PATH，或在设置里关闭音频清洗")

    paths.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    temp = paths.TEMP_DIR / f"clean_{uuid.uuid4().hex}.{ext}"
    try:
        ffmpeg.clean_audio(source, temp, ext)
        return temp, file_md5(temp)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def import_file(source: Path, library: Library, clean: bool = True) -> ImportOutcome:
    path = Path(source)
    try:
        path = path.resolve()
    except OSError:
        return ImportOutcome(error="文件路径无法解析")

    if not path.exists() or not path.is_file():
        return ImportOutcome(error="文件不存在")

    ext = path.suffix.lower().lstrip(".")
    if ext not in AUDIO_EXTS:
        return ImportOutcome(error=f"不支持的格式：.{ext}")

    prepared: Path | None = None
    try:
        prepared, md5 = _prepare(path, ext, clean)

        if md5 in library.musics:
            return ImportOutcome(duplicate=True)

        target = paths.music_path(md5, ext)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            if prepared == path:
                shutil.copy2(prepared, target)
            else:
                shutil.move(str(prepared), str(target))
                prepared = None

        title, author_names = parse_filename(path.stem)
        author_uids = [ensure_author(library, name) for name in author_names]
        now = int(time.time())
        music = Music(
            md5=md5,
            names=[title or "未命名"],
            authors=author_uids,
            tags=[],
            ext=ext,
            duration_ms=ffmpeg.probe_duration_ms(target),
            size=target.stat().st_size,
            created_at=now,
            updated_at=now,
        )
        library.upsert_music(music)
        return ImportOutcome(music=music)
    except ActionError as error:
        return ImportOutcome(error=str(error))
    except OSError as error:
        return ImportOutcome(error=f"文件读写失败：{error}")
    finally:
        if prepared is not None and prepared != path:
            prepared.unlink(missing_ok=True)
