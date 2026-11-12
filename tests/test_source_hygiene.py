"""静态守卫：分层不被破坏，入口保持薄。"""

from __future__ import annotations

import ast

from app import paths

FORBIDDEN_IN_CORE = ("webview", "PySide6", "PyQt5", "PyQt6")


def _imports(path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_core_has_no_ui_imports():
    for path in (paths.PACKAGE_DIR / "core").rglob("*.py"):
        bad = [name for name in _imports(path) if name.split(".")[0] in FORBIDDEN_IN_CORE]
        assert not bad, f"{path.name} 引入了界面库：{bad}"


def test_system_has_no_ui_imports():
    for path in (paths.PACKAGE_DIR / "system").rglob("*.py"):
        bad = [name for name in _imports(path) if name.split(".")[0] in FORBIDDEN_IN_CORE]
        assert not bad, f"{path.name} 引入了界面库：{bad}"


def test_no_working_directory_changes():
    for path in paths.PACKAGE_DIR.rglob("*.py"):
        assert "os.chdir" not in path.read_text(encoding="utf-8"), path.name


def test_manager_entry_stays_thin():
    lines = paths.MANAGER_ENTRY.read_text(encoding="utf-8").strip().splitlines()

    assert len(lines) < 30
