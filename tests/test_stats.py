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


def test_full_plays_counts_only_unskipped_runs(tmp_path):
    store = StatsStore(tmp_path / "stats")
    for skipped in (True, False, True, False, False):
        store.record(PLAYLIST, SONG, skipped=skipped, window=100)

    entry = store.load(PLAYLIST)[SONG]

    assert entry.records == "10100"
    assert entry.full_plays == 3
    assert store.summary(PLAYLIST)[SONG]["full_plays"] == 3


def test_full_plays_survive_reload_and_merge_on_replace(tmp_path):
    store = StatsStore(tmp_path / "stats")
    store.record(PLAYLIST, SONG, skipped=False, window=100)
    other = "t" * 32
    store.record(PLAYLIST, other, skipped=False, window=100)

    assert store.move_key(PLAYLIST, other, SONG, 100) is True

    entry = store.load(PLAYLIST)[SONG]
    assert entry.full_plays == 2
    assert entry.records == "00"


def test_missing_full_plays_field_defaults_to_zero(tmp_path):
    import json

    store = StatsStore(tmp_path / "stats")
    store.directory.mkdir(parents=True, exist_ok=True)
    store.path_for(PLAYLIST).write_text(
        json.dumps({"version": 1, "playlist": PLAYLIST, "songs": {SONG: {"records": "01"}}}),
        encoding="utf-8",
    )

    entry = store.load(PLAYLIST)[SONG]

    assert entry.full_plays == 0
    assert entry.records == "01"
