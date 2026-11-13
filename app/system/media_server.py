"""本地媒体服务。

``<audio>`` 要能拖动进度条，就必须支持 Range 请求；``file://`` 下 Chromium
不给按字节跳转。这里起一个只监听 127.0.0.1 的小服务，端口随机、路径里带
一次性令牌，窗口关闭即停。不做目录列表，只服务 ``assets/music`` 下的文件。
"""

from __future__ import annotations

import mimetypes
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote

from loguru import logger

CHUNK = 64 * 1024


class _Handler(BaseHTTPRequestHandler):
    server_version = "MusicPlayerMedia/1.0"
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 —— BaseHTTPRequestHandler 的约定
        server = self.server
        parts = self.path.split("/", 3)
        if len(parts) != 4 or parts[1] != "media" or parts[2] != server.token:
            self.send_error(404)
            return

        root: Path = server.root
        try:
            path = (root / unquote(parts[3])).resolve()
        except OSError:
            self.send_error(404)
            return
        if path.parent != root.resolve() or not path.is_file():
            self.send_error(404)
            return

        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        header = self.headers.get("Range", "")
        if header.startswith("bytes="):
            spec = header[6:].split(",", 1)[0].strip()
            left, _, right = spec.partition("-")
            try:
                if left:
                    start = int(left)
                    end = int(right) if right else size - 1
                elif right:
                    start = max(0, size - int(right))
                status = 206
            except ValueError:
                start, end, status = 0, size - 1, 200

        if start >= size:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        end = min(end, size - 1)
        length = end - start + 1
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()

        try:
            with open(path, "rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = handle.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            return  # 用户拖动进度条会主动断开旧请求，属于正常现象

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


class MediaServer:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.token = secrets.token_urlsafe(18)
        self.port = 0
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            return
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        server.daemon_threads = True
        server.root = self.root  # type: ignore[attr-defined]
        server.token = self.token  # type: ignore[attr-defined]
        self._server = server
        self.port = server.server_address[1]
        self._thread = threading.Thread(target=server.serve_forever, name="media", daemon=True)
        self._thread.start()
        logger.info("媒体服务已启动：127.0.0.1:{}", self.port)

    def url(self, name: str) -> str:
        self.start()
        return f"http://127.0.0.1:{self.port}/media/{self.token}/{quote(name)}"

    def stop(self) -> None:
        server = self._server
        if server is None:
            return
        server.shutdown()
        server.server_close()
        self._server = None
        self._thread = None
        logger.info("媒体服务已停止")
