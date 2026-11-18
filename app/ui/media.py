"""按目录分组的本地媒体服务。

音乐的媒体服务只服务一个目录；番茄钟有背景、提示音、环境音三个目录，各自
起一个小服务比把 ``MediaServer`` 改成多根目录更简单，也不会影响已有的音乐
路径。每个目录只在第一次要 URL 时启动，窗口关闭时一起停。
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from app.system.media_server import MediaServer


class MediaHub:
    def __init__(self) -> None:
        self._servers: dict[str, MediaServer] = {}

    def url(self, root: Path, name: str) -> str:
        key = str(Path(root))
        server = self._servers.get(key)
        if server is None:
            server = MediaServer(Path(root))
            self._servers[key] = server
        return server.url(name)

    def stop(self) -> None:
        for server in self._servers.values():
            try:
                server.stop()
            except Exception:
                logger.exception("停止番茄钟媒体服务失败")
        self._servers.clear()
