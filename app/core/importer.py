"""导入流水线。

选择文件 → 校验后缀 → 清洗（可选） → 计算 MD5 → 落盘 → 写库。
清洗后的字节决定身份，所以同一个文件在不同机器上导入应当得到同一个 MD5。

流水线拆成「准备」与「提交」两段：准备要跑 FFmpeg、算 MD5、读时长，动辄几秒；
提交只把文件挪进库、往内存里加一条记录，是毫秒级的。调用方（管理器的导入线程）
可以在准备阶段放开锁，只在提交时短暂持有，这样界面在导入期间仍然能读快照，
也不会撞上「字典在迭代时被改变」。
"""

from __future__ import annotations

import hashlib
import shutil
import time
import uuid
from dataclasses import dataclass, field
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


@dataclass(slots=True)
class PreparedImport:
    """一个已经算好身份、等待入库的文件。"""

    source: Path
    md5: str
    ext: str
    duration_ms: int
    size: int
    title: str
    authors: list[str] = field(default_factory=list)
    staged: Path | None = None

    def discard(self) -> None:
        """丢掉清洗产物；源文件永远不动。"""
        if self.staged is not None:
            self.staged.unlink(missing_ok=True)
            self.staged = None


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


def prepare_import(source: Path, clean: bool) -> PreparedImport:
    """把文件准备到「可以入库」的状态；失败抛 ``ActionError``，不留临时文件。"""
    path = Path(source)
    try:
        path = path.resolve()
    except OSError as error:
        raise ActionError("文件路径无法解析") from error

    if not path.exists() or not path.is_file():
        raise ActionError("文件不存在")

    ext = path.suffix.lower().lstrip(".")
    if ext not in AUDIO_EXTS:
        raise ActionError(f"不支持的格式：.{ext}")

    staged: Path | None = None
    try:
        if clean:
            if not ffmpeg.available():
                raise ActionError("未检测到 FFmpeg，请先安装并加入 PATH，或在设置里关闭音频清洗")
            paths.TEMP_DIR.mkdir(parents=True, exist_ok=True)
            staged = paths.TEMP_DIR / f"clean_{uuid.uuid4().hex}.{ext}"
            ffmpeg.clean_audio(path, staged, ext)
            payload = staged
        else:
            payload = path

        title, authors = parse_filename(path.stem)
        return PreparedImport(
            source=path,
            md5=file_md5(payload),
            ext=ext,
            duration_ms=ffmpeg.probe_duration_ms(payload),
            size=payload.stat().st_size,
            title=title,
            authors=authors,
            staged=staged,
        )
    except Exception:
        if staged is not None:
            staged.unlink(missing_ok=True)
        raise


def commit_import(
    prepared: PreparedImport,
    library: Library,
    title: str | None = None,
    authors: list[str] | None = None,
) -> ImportOutcome:
    """把准备好的文件落盘并写进内存库；重复时返回 ``duplicate``，不新建记录。"""
    try:
        if prepared.md5 in library.musics:
            return ImportOutcome(duplicate=True)

        target = paths.music_path(prepared.md5, prepared.ext)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            if prepared.staged is None:
                shutil.copy2(prepared.source, target)
            else:
                shutil.move(str(prepared.staged), str(target))
                prepared.staged = None

        final_title = (title or "").strip() or prepared.title or "未命名"
        if authors is None:
            names = prepared.authors
        else:
            names = [name.strip() for name in authors if name and name.strip()]

        author_uids = [ensure_author(library, name) for name in names]
        now = int(time.time())
        music = Music(
            md5=prepared.md5,
            names=[final_title],
            authors=author_uids,
            tags=[],
            ext=prepared.ext,
            duration_ms=prepared.duration_ms,
            size=target.stat().st_size,
            created_at=now,
            updated_at=now,
        )
        library.upsert_music(music)
        return ImportOutcome(music=music)
    finally:
        prepared.discard()


def import_file(
    source: Path,
    library: Library,
    clean: bool = True,
    title: str | None = None,
    authors: list[str] | None = None,
) -> ImportOutcome:
    """一步到位的导入：准备与提交连在一起，失败一律变成 ``error`` 字符串。"""
    try:
        prepared = prepare_import(source, clean)
    except ActionError as error:
        return ImportOutcome(error=str(error))
    except OSError as error:
        return ImportOutcome(error=f"文件读写失败：{error}")

    try:
        return commit_import(prepared, library, title, authors)
    except ActionError as error:
        return ImportOutcome(error=str(error))
    except OSError as error:
        return ImportOutcome(error=f"文件读写失败：{error}")
