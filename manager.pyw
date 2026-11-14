"""音乐库管理器入口。

双击 ``manager.bat`` 时由虚拟环境里的 ``pythonw.exe`` 执行本文件。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _run() -> None:
    from app import bootstrap

    # 传模块名而不是函数：界面库缺失这类导入错误也要落到 guard 里。
    bootstrap.guard("app.ui.manager.app", "manager")


if __name__ == "__main__":
    _run()
