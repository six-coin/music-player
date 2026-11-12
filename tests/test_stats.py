"""统计文件的读写。"""

from __future__ import annotations

from app.core.stats import StatsStore

PLAYLIST = "p" * 32
SONG = "s" * 32


def test_record_creates_file_and_appends(tmp_path):
    store = StatsStore(tmp_path / "stats")

    store.record(PLAYLIST, SONG, skipped=True, window=100)

    assert store.path_for(PLAYLIST).exists()
    songs = store.load(PLAYLIST)
    assert songs[SONG].records == "1"
    assert songs[SONG].last_played_at > 0


def test_record_trims_to_window(tmp_path):
    store = StatsStore(tmp_path / "stats")
    for _ in range(5):
        store.record(PLAYLIST, SONG, skipped=False, window=3)

    assert store.load(PLAYLIST)[SONG].records == "000"


def test_auto_skipped_is_counted_separately(tmp_path):
    store = StatsStore(tmp_path / "stats")

    store.mark_auto_skipped(PLAYLIST, SONG)

    songs = store.load(PLAYLIST)
    assert songs[SONG].records == ""
    assert songs[SONG].auto_skipped == 1


def test_reset_clears_playlist(tmp_path):
    store = StatsStore(tmp_path / "stats")
    store.record(PLAYLIST, SONG, skipped=True, window=100)

    store.reset(PLAYLIST)

    assert store.load(PLAYLIST) == {}


def test_prune_removes_unknown_songs(tmp_path):
    store = StatsStore(tmp_path / "stats")
    store.record(PLAYLIST, SONG, skipped=True, window=100)

    removed = store.prune(PLAYLIST, set())

    assert removed == 1
    assert store.load(PLAYLIST) == {}


def test_summary_reports_rate(tmp_path):
    store = StatsStore(tmp_path / "stats")
    for skipped in (True, False):
        store.record(PLAYLIST, SONG, skipped=skipped, window=100)

    summary = store.summary(PLAYLIST)[SONG]

    assert summary["total"] == 2
    assert summary["skips"] == 1
    assert summary["rate"] == 0.5
