"""GUI 임포트 스모크 테스트 (tkinter 없으면 skip)."""

import pytest


def test_gui_module_imports():
    pytest.importorskip("tkinter")
    from shortform_editor import gui
    assert hasattr(gui, "main")
    assert hasattr(gui, "App")


def test_studio_module_imports():
    pytest.importorskip("tkinter")
    from shortform_editor import studio
    assert hasattr(studio, "main")
    assert hasattr(studio, "Studio")
    # 포맷 프리셋 무결성: fmt 키와 길이 목록이 파이프라인 계약과 맞아야 함
    for cfg in studio.FORMATS.values():
        assert cfg["fmt"] in ("short", "mid", "long")
        assert cfg["default_len"] in cfg["lengths"]
