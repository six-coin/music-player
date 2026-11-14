"""VLC 薄封装：播放、停止、关闭（不依赖真实 VLC）。"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from app.system.vlc import VlcPlayer, VlcUnavailable


class FakeMediaPlayer:
    def __init__(self) -> None:
        self.playing = False
        self.media = None
        self.stopped = 0
        self.released = False
        self.volume_calls: list[int] = []

    def set_media(self, media) -> None:
        self.media = media

    def play(self) -> int:
        self.playing = True
        return 0

    def is_playing(self) -> bool:
        return self.playing

    def audio_set_volume(self, value: int) -> int:
        self.volume_calls.append(value)
        return 0

    def stop(self) -> None:
        self.playing = False
        self.stopped += 1

    def release(self) -> None:
        self.released = True


class FakeInstance:
    def __init__(self) -> None:
        self.player = FakeMediaPlayer()
        self.released = False

    def media_player_new(self) -> FakeMediaPlayer:
        return self.player

    def media_new(self, path: str) -> str:
        return path

    def release(self) -> None:
        self.released = True


def install_fake_vlc(monkeypatch) -> FakeInstance:
    instance = FakeInstance()
    module = types.SimpleNamespace(Instance=lambda *args: instance)
    monkeypatch.setitem(sys.modules, "vlc", module)
    return instance


def test_play_sets_media_and_starts(monkeypatch, tmp_path):
    instance = install_fake_vlc(monkeypatch)
    player = VlcPlayer()
    player.open()

    assert player.play(tmp_path / "a.mp3") is True
    assert instance.player.media == str(tmp_path / "a.mp3")
    assert player.is_playing() is True

    player.close()


def test_stop_and_close_release_everything(monkeypatch, tmp_path):
    instance = install_fake_vlc(monkeypatch)
    player = VlcPlayer()
    player.open()
    player.play(tmp_path / "a.mp3")

    player.stop()
    assert player.is_playing() is False

    player.close()
    assert instance.player.released is True
    assert instance.released is True


def test_play_before_open_raises():
    with pytest.raises(VlcUnavailable):
        VlcPlayer().play(Path("x.mp3"))


def test_volume_is_never_touched(monkeypatch, tmp_path):
    """程序不替用户设音量：整个播放周期一次 audio_set_volume 都不该有。"""
    instance = install_fake_vlc(monkeypatch)
    player = VlcPlayer()
    player.open()

    player.play(tmp_path / "a.mp3")
    player.stop()
    player.play(tmp_path / "b.mp3")
    player.is_playing()

    assert instance.player.volume_calls == []
    player.close()
