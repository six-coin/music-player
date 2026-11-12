"""设置的读写、夹取与未知键保留。"""

from __future__ import annotations

import json

from app.settings import SettingsStore


def test_first_load_creates_file_with_defaults(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)

    warnings = store.load()

    assert warnings == []
    assert path.exists()
    assert store.data["common"]["theme"] == "system"
    assert store.data["simple"]["order"] == "shuffle"
    assert store.data["player"]["volume"] == 0.8


def test_values_are_clamped(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.load()

    store.update(
        {
            "common": {"theme": "neon", "adaptation": {"window": 5, "min_plays": 900, "base": 3}},
            "simple": {"order": "sequential"},
            "player": {"order": "nope", "volume": 4},
        }
    )

    assert store.data["common"]["theme"] == "system"
    assert store.data["common"]["adaptation"]["window"] == 10
    assert store.data["common"]["adaptation"]["min_plays"] == 10
    assert store.data["common"]["adaptation"]["base"] == 0.99
    assert store.data["simple"]["order"] == "shuffle"
    assert store.data["player"]["order"] == "shuffle"
    assert store.data["player"]["volume"] == 1.0


def test_unknown_keys_survive_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"custom": {"note": "keep me"}}), encoding="utf-8")

    store = SettingsStore(path)
    store.load()
    store.update({"common": {"theme": "dark"}})

    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["custom"] == {"note": "keep me"}
    assert reloaded["common"]["theme"] == "dark"


def test_broken_json_falls_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{ not json", encoding="utf-8")

    store = SettingsStore(path)
    warnings = store.load()

    assert warnings
    assert store.data["common"]["theme"] == "system"


def test_get_supports_default(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.load()

    assert store.get("common", "theme") == "system"
    assert store.get("common", "missing", default="fallback") == "fallback"
