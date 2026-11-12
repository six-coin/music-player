"""测试公共设施：固定语言，提供构造歌曲的工厂。"""

from __future__ import annotations

import pytest

from app import i18n
from app.models import Music


@pytest.fixture(autouse=True)
def fixed_language():
    i18n.set_language("zh-CN")
    yield
    i18n.set_language("zh-CN")


@pytest.fixture
def music_factory():
    def build(char: str = "a", **overrides) -> Music:
        payload = {
            "md5": char * 32,
            "names": [f"Song {char}"],
            "authors": [],
            "tags": [],
            "ext": "mp3",
            "duration_ms": 1000,
            "size": 100,
            "created_at": 1,
            "updated_at": 1,
        }
        payload.update(overrides)
        return Music(**payload)

    return build
