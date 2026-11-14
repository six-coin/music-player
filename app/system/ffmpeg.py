"""FFmpeg 调用。

不做转码，只重封装并丢弃元数据。缺 FFmpeg 时明确报错，不静默降级——
静默降级会让同一个文件在不同机器上算出不同的 MD5。
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


def clean_audio(source: Path, target: Path, ext: str) -> None:
    """重封装到目标文件：只保留音频流，丢弃全部元数据。"""
    binary = ffmpeg_path()
    if binary is None:
        raise ActionError("未检测到 FFmpeg，请先安装并加入 PATH")

    arguments = [binary, "-hide_banner", "-loglevel", "error", "-y"]
    arguments += ["-i", str(source), "-map", "0:a"]
    arguments += ["-c", "copy", "-map_metadata", "-1", "-fflags", "+bitexact"]
    if ext == "mp3":
        arguments += ["-write_id3v1", "0", "-id3v2_version", "0", "-write_xing", "0", "-f", "mp3"]
    elif ext == "m4a":
        arguments += ["-movflags", "+faststart", "-f", "mp4"]
    else:
        raise ActionError(f"不支持的音频格式：{ext}")
    arguments.append(str(target))

    result = _run(arguments)
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        message = detail[-1] if detail else "未知错误"
        raise ActionError(f"FFmpeg 处理失败：{message}")


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
