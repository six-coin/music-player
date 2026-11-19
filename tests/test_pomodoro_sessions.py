"""番茄钟的播放记录：追加、读取、坏记录跳过。"""

from __future__ import annotations

import json

from app.core.pomodoro_sessions import MAX_SESSIONS, SessionLog, SessionRecord
from app.models import new_uid


def _record(uid: str, focus_ms: int = 1500_000) -> SessionRecord:
    return SessionRecord(
        uid=uid,
        started_at=1_790_000_000,
        ended_at=1_790_001_500,
        focus_ms=focus_ms,
        rest_ms=300_000,
    )


def test_append_and_reload(tmp_path):
    uid = new_uid()
    log = SessionLog(tmp_path / "pomodoro-sessions.json")
    assert log.load() == []

    log.append(_record(uid))

    second = SessionLog(tmp_path / "pomodoro-sessions.json")
    assert second.load() == []
    assert [record.uid for record in second.entries()] == [uid]
    assert second.entries()[0].focus_ms == 1500_000


def test_append_keeps_the_previous_records(tmp_path):
    log = SessionLog(tmp_path / "pomodoro-sessions.json")
    log.load()
    first, second = new_uid(), new_uid()

    log.append(_record(first))
    log.append(_record(second))

    assert [record.uid for record in log.entries()] == [first, second]


def test_records_are_capped(tmp_path):
    log = SessionLog(tmp_path / "pomodoro-sessions.json")
    log.load()
    records = [_record(new_uid()) for _ in range(MAX_SESSIONS + 5)]
    log.records = records
    log.save()

    reloaded = SessionLog(tmp_path / "pomodoro-sessions.json")
    assert reloaded.load() == []

    assert len(reloaded.entries()) == MAX_SESSIONS
    assert reloaded.entries()[-1].uid == records[-1].uid


def test_broken_entries_are_skipped(tmp_path):
    path = tmp_path / "pomodoro-sessions.json"
    uid = new_uid()
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "sessions": [
                    {"uid": uid, "started_at": 10, "ended_at": 20, "focus_ms": 5, "rest_ms": 6},
                    {"uid": "not-a-uid", "started_at": 10},
                    "nonsense",
                ],
            }
        ),
        encoding="utf-8",
    )

    log = SessionLog(path)
    warnings = log.load()

    assert warnings
    assert [record.uid for record in log.entries()] == [uid]


def test_missing_file_is_not_created(tmp_path):
    path = tmp_path / "pomodoro-sessions.json"
    log = SessionLog(path)

    assert log.load() == []

    assert not path.exists()


def test_times_are_normalized(tmp_path):
    log = SessionLog(tmp_path / "pomodoro-sessions.json")
    log.load()

    log.append(
        SessionRecord(
            uid=new_uid(),
            started_at=100,
            ended_at=50,
            focus_ms=-1,
            rest_ms=-1,
        )
    )

    record = log.entries()[0]
    assert record.ended_at == 100
    assert (record.focus_ms, record.rest_ms) == (0, 0)
