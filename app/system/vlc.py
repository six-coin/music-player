"""VLC 播放器的薄接口。

只暴露 ``play`` / ``is_playing`` / ``stop`` / ``close`` 四个方法，界面层不直接
碰 python-vlc。导入 python-vlc 放在方法里：用户机器上没装 VLC 时，要在启动
阶段给出一句人话，而不是在 import 阶段抛一长串 traceback。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

DOWNLOAD_URL = "https://www.videolan.org/vlc/"

# 关闭视频输出与界面：这是个只放音频的程序，多余的模块只会拖慢启动。
_ARGS = ("--no-video", "--quiet", "--intf=dummy")


class VlcUnavailable(Exception):
    """找不到 libvlc，或 libvlc 无法初始化。"""


class Player(Protocol):
    """播放循环只依赖这三个方法，测试里换成假实现。"""

    def play(self, path: Path) -> bool: ...

    def is_playing(self) -> bool: ...

    def stop(self) -> None: ...


def probe() -> str:
    """返回 VLC 版本号；不可用就抛 ``VlcUnavailable``，由调用方打印安装指引。"""
    try:
        import vlc
    except Exception as error:  # python-vlc 找不到 libvlc 时抛 NameError / OSError
        raise VlcUnavailable(str(error) or "没有找到 libvlc.dll") from error
    try:
        version = vlc.libvlc_get_version()
    except Exception as error:
        raise VlcUnavailable(str(error) or "libvlc 无法加载") from error
    if isinstance(version, bytes):
        return version.decode("ascii", "replace").strip("\x00 ")
    return str(version)


class VlcPlayer:
    """一个实例一个 MediaPlayer；``close()`` 之后不能再 ``play()``。"""

    def __init__(self, extra_args: tuple[str, ...] = ()) -> None:
        self._instance: Any = None
        self._player: Any = None
        self._args = (*_ARGS, *extra_args)

    def open(self) -> None:
        try:
            import vlc
        except Exception as error:
            raise VlcUnavailable(str(error) or "没有找到 libvlc.dll") from error
        instance = vlc.Instance(*self._args)
        if instance is None:
            raise VlcUnavailable("VLC 无法初始化")
        player = instance.media_player_new()
        if player is None:
            instance.release()
            raise VlcUnavailable("VLC 无法创建播放器")
        self._instance = instance
        self._player = player

    def play(self, path: Path) -> bool:
        if self._instance is None or self._player is None:
            raise VlcUnavailable("播放器还没有初始化")
        media = self._instance.media_new(str(path))
        self._player.set_media(media)
        return self._player.play() == 0

    def is_playing(self) -> bool:
        if self._player is None:
            return False
        return bool(self._player.is_playing())

    def stop(self) -> None:
        if self._player is None:
            return
        try:
            self._player.stop()
        except Exception:  # 关闭窗口时 VLC 可能已经自己停了，这里不值得报错
            pass

    def close(self) -> None:
        if self._player is not None:
            self.stop()
            try:
                self._player.release()
            except Exception:  # 同上：退出路径上的清理失败不阻断进程结束
                pass
            self._player = None
        if self._instance is not None:
            try:
                self._instance.release()
            except Exception:  # 同上
                pass
            self._instance = None
