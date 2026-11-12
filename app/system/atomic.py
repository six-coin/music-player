"""JSON 读写。

写入一律走「临时文件 + 原子替换」：中途崩溃不会留下半个文件，
读者也不会看到写了一半的内容。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.errors import ConfigError


def read_json(path: Path) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as error:
        raise ConfigError(f"文件不存在：{path}") from error
    except OSError as error:
        raise ConfigError(f"读取文件失败：{path}（{error}）") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"JSON 格式错误：{path}（第 {error.lineno} 行：{error.msg}）") from error


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=4, ensure_ascii=False)
            handle.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
