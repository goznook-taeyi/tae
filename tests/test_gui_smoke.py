"""GUI 임포트 스모크 테스트 (tkinter 없으면 skip)."""

import pytest


def test_gui_module_imports():
    pytest.importorskip("tkinter")
    from shortform_editor import gui
    assert hasattr(gui, "main")
    assert hasattr(gui, "App")
