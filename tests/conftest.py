"""测试公共设施：固定语言，提供构造歌曲的工厂。"""

from __future__ import annotations

import pytest

from app import i18n, paths
from app.models import Music


@pytest.fixture(autouse=True)
def fixed_language():
    i18n.set_language("zh-CN")
    yield
    i18n.set_language("zh-CN")


@pytest.fixture(autouse=True)
def isolated_media(tmp_path_factory, monkeypatch):
    """测试绝不碰真实的 assets 目录：用户库里的音频不该被测试删掉或数成孤儿。"""
    root = tmp_path_factory.mktemp("media")
    monkeypatch.setattr(paths, "ASSETS_DIR", root)
    monkeypatch.setattr(paths, "MUSIC_DIR", root / "music")
    monkeypatch.setattr(paths, "TEMP_DIR", root / "temp")
    yield root


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
