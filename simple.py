"""轻量音乐播放器入口。

双击 ``simple.bat`` 时由虚拟环境里的 ``python.exe`` 执行本文件。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _run() -> None:
    from app.cli.simple import main

    sys.exit(main())


if __name__ == "__main__":
    _run()
