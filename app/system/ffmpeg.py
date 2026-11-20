"""FFmpeg 调用。

音乐导入只重封装并丢弃元数据，不转码——清洗后的字节决定身份，同一个文件在
不同机器上必须算出同一个 MD5。番茄钟的资源是另一回事：背景要转成 PNG/MP4、
环境音要裁剪与交叉淡化，这些都必须重编码，函数名里写清楚。

缺 FFmpeg 时明确报错，不静默降级。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.errors import ActionError

_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

#: 视频统一转成这个编码：WebView2 对 H.264 的支持最稳。
VIDEO_CODEC = "libx264"


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def ffprobe_path() -> str | None:
    return shutil.which("ffprobe")


def available() -> bool:
    return ffmpeg_path() is not None


def _run(arguments: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=_NO_WINDOW,
            timeout=timeout,
            check=False,
        )
    except OSError as error:
        raise ActionError(f"无法启动 FFmpeg：{error}") from error
    except subprocess.TimeoutExpired as error:
        raise ActionError("FFmpeg 处理超时，文件可能过大或已损坏") from error


def _binary() -> str:
    binary = ffmpeg_path()
    if binary is None:
        raise ActionError("未检测到 FFmpeg，请先安装并加入 PATH")
    return binary


def _failure(result: subprocess.CompletedProcess) -> ActionError:
    detail = (result.stderr or "").strip().splitlines()
    message = detail[-1] if detail else "未知错误"
    return ActionError(f"FFmpeg 处理失败：{message}")


def _seconds(milliseconds: int) -> str:
    """毫秒转成 ffmpeg 认的秒，保留三位小数。"""
    return f"{max(0, int(milliseconds)) / 1000:.3f}"


def clean_audio(source: Path, target: Path, ext: str) -> None:
    """重封装到目标文件：只保留音频流，丢弃全部元数据。"""
    arguments = [_binary(), "-hide_banner", "-loglevel", "error", "-y"]
    arguments += ["-i", str(source), "-map", "0:a"]
    arguments += ["-c", "copy", "-map_metadata", "-1", "-fflags", "+bitexact"]
    if ext == "mp3":
        arguments += ["-write_id3v1", "0", "-id3v2_version", "0", "-write_xing", "0", "-f", "mp3"]
    elif ext == "m4a":
        arguments += ["-movflags", "+faststart", "-f", "mp4"]
    elif ext == "ogg":
        arguments += ["-f", "ogg"]
    else:
        raise ActionError(f"不支持的音频格式：{ext}")
    arguments.append(str(target))

    result = _run(arguments)
    if result.returncode != 0:
        raise _failure(result)


def probe_duration_ms(path: Path) -> int:
    """读不到时长就返回 0，界面显示为未知，不阻断导入。"""
    binary = ffprobe_path()
    if binary is None:
        return 0
    result = _run(
        [
            binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout=30,
    )
    if result.returncode != 0:
        return 0
    try:
        return int(float(result.stdout.strip()) * 1000)
    except ValueError:
        return 0


def probe_stream(path: Path) -> dict[str, Any]:
    """用 ffprobe 读音频流参数，给「虚标检测」用。

    返回 ``{"sample_rate", "bit_rate", "codec", "duration", "size"}``，
    读不出来的字段缺省为 0 / 空串。ffprobe 不可用时返回空字典——调用方据此
    跳过这项检查，而不是把整个深检判成失败。
    """
    binary = ffprobe_path()
    if binary is None:
        return {}
    result = _run(
        [
            binary,
            "-v",
            "error",
            "-show_entries",
            "stream=sample_rate,bit_rate,codec_name:format=duration,bit_rate,size",
            "-select_streams",
            "a:0",
            "-of",
            "json",
            str(path),
        ],
        timeout=30,
    )
    if result.returncode != 0:
        return {}
    try:
        raw = json.loads(result.stdout or "{}")
    except ValueError:
        return {}
    streams = raw.get("streams") or []
    stream = streams[0] if isinstance(streams, list) and streams else {}
    container = raw.get("format") or {}
    if not isinstance(stream, dict) or not isinstance(container, dict):
        return {}
    return {
        "sample_rate": _as_int(stream.get("sample_rate")),
        "bit_rate": _as_int(stream.get("bit_rate")),
        "codec": str(stream.get("codec_name") or ""),
        "duration": _as_float(container.get("duration")),
        "size": _as_int(container.get("size")),
        "container_bit_rate": _as_int(container.get("bit_rate")),
    }


def probe_media(path: Path) -> dict[str, Any]:
    """读视频/图片/音频的通用信息，番茄钟导入用。

    返回 ``duration_ms`` / ``width`` / ``height`` / ``size`` / ``has_audio`` /
    ``video_codec`` / ``audio_codec``。ffprobe 不可用时抛错：导入必须知道时长
    才能算中点，不能像「虚标检测」那样静默跳过。
    """
    binary = ffprobe_path()
    if binary is None:
        raise ActionError("未检测到 ffprobe，请先安装并加入 PATH")
    result = _run(
        [
            binary,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,width,height:format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        timeout=60,
    )
    if result.returncode != 0:
        raise _failure(result)
    try:
        raw = json.loads(result.stdout or "{}")
    except ValueError as error:
        raise ActionError("ffprobe 返回的内容无法解析") from error

    streams = raw.get("streams") or []
    container = raw.get("format") or {}
    video: dict[str, Any] = {}
    audio: dict[str, Any] = {}
    for stream in streams if isinstance(streams, list) else []:
        if not isinstance(stream, dict):
            continue
        kind = stream.get("codec_type")
        if kind == "video" and not video:
            video = stream
        elif kind == "audio" and not audio:
            audio = stream
    return {
        "duration_ms": int(_as_float(container.get("duration")) * 1000),
        "size": _as_int(container.get("size")) or (path.stat().st_size if path.exists() else 0),
        "width": _as_int(video.get("width")),
        "height": _as_int(video.get("height")),
        "has_audio": bool(audio),
        "video_codec": str(video.get("codec_name") or ""),
        "audio_codec": str(audio.get("codec_name") or ""),
    }


def convert_image_to_png(source: Path, target: Path) -> None:
    """取第一帧转 PNG。动图只保留首帧——背景是静帧，动图没有意义。"""
    arguments = [
        _binary(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-map_metadata",
        "-1",
        "-fflags",
        "+bitexact",
        "-c:v",
        "png",
        "-f",
        "image2",
        str(target),
    ]
    result = _run(arguments, timeout=120)
    if result.returncode != 0:
        raise _failure(result)


def _video_encode_args() -> list[str]:
    # 背景视频是循环播放的底图，不值得为画质用 medium；veryfast + CRF 23
    # 在 1080p 上通常能把转码时间压到原来的三分之一左右。
    return [
        "-an",
        "-c:v",
        VIDEO_CODEC,
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-map_metadata",
        "-1",
        "-fflags",
        "+bitexact",
    ]


def remux_video(source: Path, target: Path) -> None:
    """不裁剪、不淡化，只去掉音轨与元数据。

    H.264 的 MP4/MOV 直接拷贝视频流，几秒就完成；其余格式重编码成 H.264，
    保证 WebView2 一定能播。
    """
    info = probe_media(source)
    copy_video = info["video_codec"] == "h264" and source.suffix.lower() in (".mp4", ".mov")
    arguments = [_binary(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
    if copy_video:
        arguments += ["-map", "0:v:0", "-c:v", "copy"]
    else:
        arguments += ["-map", "0:v:0", *_video_encode_args()]
    if copy_video:
        arguments += [
            "-an",
            "-movflags",
            "+faststart",
            "-map_metadata",
            "-1",
            "-fflags",
            "+bitexact",
        ]
    arguments.append(str(target))
    result = _run(arguments, timeout=600)
    if result.returncode != 0:
        raise _failure(result)


def transcode_video(
    source: Path,
    target: Path,
    *,
    start_ms: int = 0,
    end_ms: int = 0,
    crossfade: bool = False,
    fade_ms: int = 3000,
) -> None:
    """裁剪视频，可选做「从中点切开、B+A 重排 + 交叉淡化」的循环处理。

    ``end_ms`` 为 0 表示到片尾。交叉淡化会让成片比裁剪后的片段短 ``fade`` 秒：
    这是 xfade 的固有结果，换来的是无缝循环。
    """
    info = probe_media(source)
    total = info["duration_ms"]
    start = max(0, min(start_ms, max(0, total - 100)))
    end = total if end_ms <= start else min(end_ms, total)
    duration = max(100, end - start)

    arguments = [_binary(), "-hide_banner", "-loglevel", "error", "-y"]
    if start > 0:
        arguments += ["-ss", _seconds(start)]
    if end < total:
        arguments += ["-to", _seconds(end)]
    arguments += ["-i", str(source)]

    if crossfade and duration >= 400:
        half = duration / 2000  # 秒
        fade = min(max(0.1, fade_ms / 1000), max(0.1, half - 0.05))
        offset = max(0.0, half - fade)
        arguments += [
            "-filter_complex",
            (
                "[0:v]split=2[v1][v2];"
                f"[v1]trim=start={half:.3f},setpts=PTS-STARTPTS[b];"
                f"[v2]trim=end={half:.3f},setpts=PTS-STARTPTS[a];"
                f"[b][a]xfade=transition=fade:duration={fade:.3f}:offset={offset:.3f}[v]"
            ),
            "-map",
            "[v]",
            *_video_encode_args(),
        ]
    else:
        arguments += ["-map", "0:v:0", *_video_encode_args()]
    arguments.append(str(target))

    result = _run(arguments, timeout=900)
    if result.returncode != 0:
        raise _failure(result)


def _audio_encode_args(ext: str) -> list[str]:
    if ext == "mp3":
        return ["-c:a", "libmp3lame", "-q:a", "2", "-f", "mp3"]
    if ext == "ogg":
        return ["-c:a", "libvorbis", "-q:a", "5", "-f", "ogg"]
    raise ActionError(f"不支持的音频格式：{ext}")


def transcode_audio(
    source: Path,
    target: Path,
    ext: str,
    *,
    start_ms: int = 0,
    end_ms: int = 0,
    crossfade: bool = False,
    fade_ms: int = 3000,
) -> None:
    """裁剪环境音，可选「B+A + acrossfade」的循环处理。"""
    info = probe_media(source)
    total = info["duration_ms"]
    start = max(0, min(start_ms, max(0, total - 100)))
    end = total if end_ms <= start else min(end_ms, total)
    duration = max(100, end - start)

    arguments = [_binary(), "-hide_banner", "-loglevel", "error", "-y"]
    if start > 0:
        arguments += ["-ss", _seconds(start)]
    if end < total:
        arguments += ["-to", _seconds(end)]
    arguments += ["-i", str(source)]

    if crossfade and duration >= 400:
        half = duration / 2000
        fade = min(max(0.1, fade_ms / 1000), max(0.1, half - 0.05))
        arguments += [
            "-filter_complex",
            (
                "[0:a]asplit=2[a1][a2];"
                f"[a1]atrim=start={half:.3f},asetpts=PTS-STARTPTS[b];"
                f"[a2]atrim=end={half:.3f},asetpts=PTS-STARTPTS[a];"
                # qsin 是等功率曲线：两段互不相关的底噪叠在一起时，功率保持 1，
                # 接缝处不会像线性淡化（tri）那样掉 3 dB，听起来就是「声音小了
                # 一下」。
                f"[b][a]acrossfade=d={fade:.3f}:c1=qsin:c2=qsin[a]"
            ),
            "-map",
            "[a]",
            "-vn",
            *_audio_encode_args(ext),
        ]
    else:
        arguments += ["-map", "0:a:0", "-vn", *_audio_encode_args(ext)]
    arguments += ["-map_metadata", "-1", "-fflags", "+bitexact"]
    arguments.append(str(target))

    result = _run(arguments, timeout=900)
    if result.returncode != 0:
        raise _failure(result)


def extract_audio_to_mp3(source: Path, target: Path) -> None:
    """MP4 转 MP3：只取第一条音轨，丢掉视频与元数据。"""
    arguments = [
        _binary(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "2",
        "-map_metadata",
        "-1",
        "-fflags",
        "+bitexact",
        "-f",
        "mp3",
        str(target),
    ]
    result = _run(arguments, timeout=600)
    if result.returncode != 0:
        raise _failure(result)


def _as_int(value: object) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def _as_float(value: object) -> float:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return 0.0
    return number if number == number else 0.0
