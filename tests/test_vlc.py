"""VLC 薄封装的音量行为（不依赖真实 VLC）。"""

from __future__ import annotations

import sys
import types

from app.system.vlc import VlcPlayer


class FakeMediaPlayer:
    def __init__(self) -> None:
        self.volume: int | None = None
        self.volume_calls: list[int] = []
        self.playing = False
        self.media = None

    def set_media(self, media) -> None:
        self.media = media

    def play(self) -> int:
        self.playing = True
        return 0

    def is_playing(self) -> bool:
        return self.playing

    def audio_set_volume(self, value: int) -> int:
        self.volume_calls.append(value)
        self.volume = value
        return 0

    def stop(self) -> None:
        self.playing = False

    def release(self) -> None:
        pass


class FakeInstance:
    def __init__(self) -> None:
        self.player = FakeMediaPlayer()

    def media_player_new(self) -> FakeMediaPlayer:
        return self.player

    def media_new(self, path: str) -> str:
        return path

    def release(self) -> None:
        pass


def install_fake_vlc(monkeypatch) -> FakeInstance:
    instance = FakeInstance()
    module = types.SimpleNamespace(Instance=lambda *args: instance)
    monkeypatch.setitem(sys.modules, "vlc", module)
    return instance


def test_volume_is_applied_when_playback_starts(monkeypatch, tmp_path):
    instance = install_fake_vlc(monkeypatch)
    player = VlcPlayer(volume=0.35)
    player.open()

    assert player.play(tmp_path / "a.mp3") is True
    assert instance.player.volume == 35

    player.close()


def test_volume_is_retried_after_audio_output_is_ready(monkeypatch, tmp_path):
    instance = install_fake_vlc(monkeypatch)
    attempts: list[int] = []

    def audio_set_volume(value: int) -> int:
        attempts.append(value)
        return -1 if len(attempts) == 1 else 0

    instance.player.audio_set_volume = audio_set_volume  # type: ignore[method-assign]
    player = VlcPlayer(volume=0.2)
    player.open()
    player.play(tmp_path / "a.mp3")

    assert attempts == [20]
    assert player.is_playing() is True
    assert attempts == [20, 20]

    player.close()
