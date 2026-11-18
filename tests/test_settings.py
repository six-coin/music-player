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
    assert store.data["common"]["theme"] == "light"
    assert store.data["simple"]["order"] == "shuffle"
    assert store.data["player"]["volume"] == 0.2


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

    assert store.data["common"]["theme"] == "light"
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
    assert store.data["common"]["theme"] == "light"


def test_get_supports_default(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.load()

    assert store.get("common", "theme") == "light"
    assert store.get("common", "missing", default="fallback") == "fallback"


def test_debug_flag_defaults_off(tmp_path):
    from app.settings import SettingsStore

    store = SettingsStore(tmp_path / "settings.json")
    store.load()

    assert store.debug_enabled() is False


def test_debug_flag_is_read_from_disk(tmp_path):
    from app.settings import SettingsStore

    store = SettingsStore(tmp_path / "settings.json")
    store.load()
    store.update({"common": {"debug": True}})

    other = SettingsStore(tmp_path / "settings.json")
    other.load()

    assert other.debug_enabled() is True


def test_audition_volume_is_clamped(tmp_path):
    from app.settings import SettingsStore

    store = SettingsStore(tmp_path / "settings.json")
    store.load()
    assert store.get("audition", "volume") == 0.2

    store.update({"audition": {"volume": 3}})
    assert store.get("audition", "volume") == 1.0


def test_simple_has_no_volume_setting(tmp_path):
    """轻量音乐播放器不再设默认音量；旧配置里留下的键顺手丢掉。"""
    store = SettingsStore(tmp_path / "settings.json")
    store.load()
    assert "volume" not in store.data["simple"]

    store.update({"simple": {"volume": 0.8}})
    assert "volume" not in store.data["simple"]


def test_broken_section_is_replaced_by_defaults(tmp_path):
    """分节被手改成标量时不该把启动拦下。"""
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"version": 1, "common": 5, "player": "x", "simple": []}),
        encoding="utf-8",
    )
    store = SettingsStore(path)

    warnings = store.load()

    assert warnings == []
    assert store.data["common"]["theme"] == "light"
    assert store.data["player"]["volume"] == 0.2
    assert store.data["simple"]["order"] == "shuffle"


def test_debug_flag_follows_the_file(tmp_path):
    """调试开关是跨进程读的；本进程改过之后缓存要立刻失效。"""
    store = SettingsStore(tmp_path / "settings.json")
    store.load()
    assert store.debug_enabled() is False

    store.update({"common": {"debug": True}})

    assert store.debug_enabled() is True


def test_shortcuts_get_defaults(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.load()

    assert store.get("player", "keys", "pick_loop") == "Ctrl+L"
    assert store.get("simple", "keys", "quit") == "Ctrl+Q"
    assert store.get("manager", "keys", "search") == "Ctrl+F"


def test_shortcuts_are_normalized(tmp_path):
    """手写的组合先认成规范形式再落盘，三端拿到的写法才一致。"""
    store = SettingsStore(tmp_path / "settings.json")
    store.load()

    store.update(
        {
            "player": {"keys": {"next": "ctrl+left", "prev": "CTRL + ARROWLEFT"}},
            "simple": {"keys": {"skip": "  ctrl+n  "}},
        }
    )

    assert store.get("player", "keys", "next") == "Ctrl+ArrowLeft"
    assert store.get("player", "keys", "prev") == "Ctrl+ArrowLeft"
    assert store.get("simple", "keys", "skip") == "Ctrl+N"


def test_unreadable_shortcut_falls_back_to_default(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.load()

    store.update({"player": {"keys": {"next": "Ctrl", "prev": 42, "pick_loop": "NoSuchKey"}}})

    assert store.get("player", "keys", "next") == "Ctrl+C"
    assert store.get("player", "keys", "prev") == "Ctrl+ArrowLeft"
    assert store.get("player", "keys", "pick_loop") == "Ctrl+L"


def test_unknown_shortcut_action_is_kept(tmp_path):
    """设置文件的未知键不丢：将来加了动作，旧版本管理器也不该把它抹掉。"""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"player": {"keys": {"future": "Ctrl+J"}}}), encoding="utf-8")

    store = SettingsStore(path)
    store.load()

    assert store.get("player", "keys", "future") == "Ctrl+J"
    assert store.get("player", "keys", "next") == "Ctrl+C"
