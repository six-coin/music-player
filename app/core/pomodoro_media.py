"""番茄钟资源的导入预处理。

三类资源三种规则：

- 背景图片：取第一帧转 PNG；背景视频：统一转 H.264 MP4，去掉音轨与元数据，
  可选「裁剪 + 从中点切开后 B+A 重排 + 交叉淡化」。
- 提示音：MP3/OGG，只清元数据，和音乐导入同一套处理。
- 环境音：MP3/OGG，可选与视频相同的裁剪/交叉淡化；选到 MP4 时先抽成 MP3。

原始文件永远不保留：处理完只把成品放进数据目录，源文件不动也不复制。
"""

from __future__ import annotations

import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from app import paths
from app.core.pomodoro import AudioAsset, Background, PomodoroStore
from app.errors import ActionError
from app.models import new_uid
from app.system import ffmpeg

IMAGE_EXTS = ("png", "jpg", "jpeg", "webp", "bmp", "gif")
VIDEO_EXTS = ("mp4", "mov", "mkv", "webm", "avi")
ENVIRONMENT_EXTS = ("mp3", "ogg", "mp4", "m4a")
RING_EXTS = ("mp3", "ogg")

DEFAULT_FADE_MS = 3000
MIN_FADE_MS = 100
MAX_FADE_MS = 30_000
MIN_CLIP_MS = 400


@dataclass(slots=True)
class SegmentOptions:
    """导入时的裁剪与淡化选项。``end_ms`` 为 0 表示到片尾。"""

    start_ms: int = 0
    end_ms: int = 0
    crossfade: bool = True
    fade_ms: int = DEFAULT_FADE_MS
    strip_only: bool = False

    @classmethod
    def from_dict(cls, raw: object) -> SegmentOptions:
        if not isinstance(raw, dict):
            return cls()
        return cls(
            start_ms=_positive(raw.get("start_ms")),
            end_ms=_positive(raw.get("end_ms")),
            crossfade=bool(raw.get("crossfade", True)),
            fade_ms=_positive(raw.get("fade_ms")) or DEFAULT_FADE_MS,
            strip_only=bool(raw.get("strip_only", False)),
        )

    def normalized(self, duration_ms: int) -> SegmentOptions:
        """把用户填的毫秒夹进片长，并保证淡化不超过半段。"""
        total = max(0, duration_ms)
        start = min(self.start_ms, max(0, total - 100))
        end = total if self.end_ms <= start else min(self.end_ms, total)
        length = max(100, end - start)
        fade = min(MAX_FADE_MS, max(MIN_FADE_MS, self.fade_ms))
        if length >= MIN_CLIP_MS:
            fade = min(fade, max(MIN_FADE_MS, length // 2 - 50))
        return SegmentOptions(
            start_ms=start,
            end_ms=end,
            crossfade=self.crossfade,
            fade_ms=fade,
            strip_only=self.strip_only,
        )


def _positive(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


def extension(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def source_kind(path: Path) -> str:
    ext = extension(path)
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in RING_EXTS or ext == "m4a":
        return "audio"
    return ""


def probe_source(path: Path) -> dict[str, object]:
    """导入对话框要用的信息：类型、时长、尺寸、大小。"""
    ext = extension(path)
    kind = source_kind(path)
    if not kind:
        raise ActionError(f"不支持的格式：.{ext}")
    info = ffmpeg.probe_media(path)
    return {
        "path": str(path),
        "name": path.stem,
        "ext": ext,
        "kind": kind,
        "duration_ms": int(info["duration_ms"]),
        "width": int(info["width"]),
        "height": int(info["height"]),
        "size": int(info["size"]),
    }


def _require_ffmpeg() -> None:
    if not ffmpeg.available():
        raise ActionError("未检测到 FFmpeg，请先安装并加入 PATH")


def _stage(suffix: str) -> Path:
    paths.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return paths.TEMP_DIR / f"pomodoro_{uuid.uuid4().hex}{suffix}"


def _move_into(stage: Path, target: Path) -> None:
    """临时目录与数据目录可能不在同一个盘，``os.replace`` 会跨盘失败。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(stage), str(target))


def _cleanup(*items: Path) -> None:
    for item in items:
        try:
            item.unlink(missing_ok=True)
        except OSError:
            pass


def _display_name(source: Path, name: str | None) -> str:
    text = (name or source.stem or "").strip()
    return text[:120] or "未命名"


def import_background(
    store: PomodoroStore,
    source: Path,
    options: SegmentOptions | None = None,
    name: str | None = None,
) -> Background:
    """导入一张背景。图片转 PNG，视频转 MP4；原始文件不保留。"""
    _require_ffmpeg()
    path = Path(source)
    if not path.is_file():
        raise ActionError("文件不存在")
    ext = extension(path)
    kind = source_kind(path)
    if kind == "audio":
        raise ActionError("背景只支持图片或视频")
    if not kind:
        raise ActionError(f"不支持的格式：.{ext}")

    uid = new_uid()
    stage = _stage(".png" if kind == "image" else ".mp4")
    final = paths.BACKGROUND_DIR / f"{uid}{stage.suffix}"
    try:
        if kind == "image":
            ffmpeg.convert_image_to_png(path, stage)
        else:
            opts = (options or SegmentOptions()).normalized(ffmpeg.probe_media(path)["duration_ms"])
            if opts.strip_only:
                ffmpeg.remux_video(path, stage)
            else:
                ffmpeg.transcode_video(
                    path,
                    stage,
                    start_ms=opts.start_ms,
                    end_ms=opts.end_ms,
                    crossfade=opts.crossfade,
                    fade_ms=opts.fade_ms,
                )
        info = ffmpeg.probe_media(stage)
        _move_into(stage, final)
        record = Background(
            uid=uid,
            name=_display_name(path, name),
            file=f"pomodoro/background/{final.name}",
            kind=kind,
            duration_ms=int(info["duration_ms"]),
            width=int(info["width"]),
            height=int(info["height"]),
            size=final.stat().st_size,
            created_at=_now(),
            updated_at=_now(),
        )
        try:
            return store.add_background(record)
        except Exception:
            _cleanup(final)
            raise
    except Exception:
        _cleanup(stage)
        raise


def import_ring(
    store: PomodoroStore,
    source: Path,
    name: str | None = None,
) -> AudioAsset:
    """提示音：MP3/OGG，只清元数据，和音乐导入同一套处理。"""
    _require_ffmpeg()
    path = Path(source)
    if not path.is_file():
        raise ActionError("文件不存在")
    ext = extension(path)
    if ext not in RING_EXTS:
        raise ActionError(f"提示音只支持 MP3/OGG，当前是 .{ext}")

    uid = new_uid()
    stage = _stage(f".{ext}")
    final = paths.RING_DIR / f"{uid}.{ext}"
    try:
        ffmpeg.clean_audio(path, stage, ext)
        info = ffmpeg.probe_media(stage)
        _move_into(stage, final)
        record = AudioAsset(
            uid=uid,
            name=_display_name(path, name),
            file=f"pomodoro/ring/{final.name}",
            ext=ext,
            duration_ms=int(info["duration_ms"]),
            size=final.stat().st_size,
            created_at=_now(),
            updated_at=_now(),
        )
        try:
            return store.add_ring(record)
        except Exception:
            _cleanup(final)
            raise
    except Exception:
        _cleanup(stage)
        raise


def import_environment(
    store: PomodoroStore,
    source: Path,
    options: SegmentOptions | None = None,
    name: str | None = None,
) -> AudioAsset:
    """环境音：MP3/OGG，或 MP4/M4A（先抽成 MP3）；可选裁剪与交叉淡化。"""
    _require_ffmpeg()
    path = Path(source)
    if not path.is_file():
        raise ActionError("文件不存在")
    ext = extension(path)
    if ext not in ENVIRONMENT_EXTS:
        raise ActionError(f"环境音只支持 MP3/OGG/MP4，当前是 .{ext}")

    work = path
    extracted: Path | None = None
    stage: Path | None = None
    final: Path | None = None
    try:
        if ext in ("mp4", "m4a"):
            extracted = _stage(".mp3")
            ffmpeg.extract_audio_to_mp3(path, extracted)
            work = extracted
            ext = "mp3"

        uid = new_uid()
        stage = _stage(f".{ext}")
        final = paths.ENVIRONMENT_DIR / f"{uid}.{ext}"
        opts = (options or SegmentOptions()).normalized(ffmpeg.probe_media(work)["duration_ms"])
        if opts.strip_only:
            ffmpeg.clean_audio(work, stage, ext)
        else:
            ffmpeg.transcode_audio(
                work,
                stage,
                ext,
                start_ms=opts.start_ms,
                end_ms=opts.end_ms,
                crossfade=opts.crossfade,
                fade_ms=opts.fade_ms,
            )
        info = ffmpeg.probe_media(stage)
        _move_into(stage, final)
        record = AudioAsset(
            uid=uid,
            name=_display_name(path, name),
            file=f"pomodoro/environment/{final.name}",
            ext=ext,
            duration_ms=int(info["duration_ms"]),
            size=final.stat().st_size,
            created_at=_now(),
            updated_at=_now(),
        )
        try:
            return store.add_environment(record)
        except Exception:
            _cleanup(final)
            raise
    except Exception:
        if stage is not None:
            _cleanup(stage)
        if extracted is not None:
            _cleanup(extracted)
        raise
    finally:
        if extracted is not None:
            _cleanup(extracted)


def _now() -> int:
    return int(time.time())
