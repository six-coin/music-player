"""崩溃弹窗的文案：固定中文，不依赖语言包。"""

from __future__ import annotations

from app import logging_setup


def test_unexpected_text_names_the_exception():
    text = logging_setup.unexpected_text(ValueError, ValueError("boom"))

    assert text.startswith("程序遇到未处理的错误：")
    assert "ValueError" in text
    assert "boom" in text


def test_crash_text_has_time_and_log_lines():
    text = logging_setup.crash_text("出事了")

    assert text.startswith("出事了")
    assert "\n时间：" in text
    assert "\n日志：" in text


def test_crash_text_does_not_look_up_the_language_table(monkeypatch):
    """语言包读不出来时，弹窗里也不能只剩一个键名。"""

    def explode(*_args, **_kwargs):
        raise AssertionError("崩溃路径不该查语言包")

    monkeypatch.setattr("app.i18n.t", explode)

    text = logging_setup.crash_text(logging_setup.unexpected_text(RuntimeError, RuntimeError("x")))

    assert "fatal." not in text
    assert "RuntimeError" in text
