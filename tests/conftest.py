"""공용 픽스처 및 테스트 더블."""

from __future__ import annotations

import numpy as np
import pytest

from app.config import Settings
from app.ocr import OcrBox, OCREngine
from app.spellcheck import SpellChecker, SpellCheckError
from app.video import SampledFrame, Segment


@pytest.fixture
def settings() -> Settings:
    return Settings()


def make_frame(index: int, ts: float, value: int, roi_hw=(80, 320)) -> SampledFrame:
    """단색 ROI 프레임 하나 생성 (value=밝기)."""
    h, w = roi_hw
    roi = np.full((h, w, 3), value, dtype=np.uint8)
    small = np.full((64, 320), value, dtype=np.uint8)
    return SampledFrame(index=index, timestamp_s=ts, roi=roi, roi_gray_small=small)


class FakeOCREngine(OCREngine):
    """호출 순서대로 스크립트된 박스를 반환."""

    def __init__(self, scripts: list[list[OcrBox]]):
        self.scripts = scripts
        self.calls = 0

    def read_boxes(self, image):
        idx = min(self.calls, len(self.scripts) - 1)
        self.calls += 1
        return list(self.scripts[idx])


class ScriptedSpellChecker(SpellChecker):
    """텍스트→이슈 매핑, 또는 지정 횟수만큼 실패."""

    def __init__(self, mapping=None, fail_times=0, fail_forever=False):
        from app.models import CheckType, SpellIssue

        self.mapping = mapping or {}
        self.fail_times = fail_times
        self.fail_forever = fail_forever
        self.calls = 0
        self._SpellIssue = SpellIssue
        self._CheckType = CheckType

    def check(self, text: str):
        self.calls += 1
        if self.fail_forever or self.calls <= self.fail_times:
            raise SpellCheckError("scripted failure")
        return self.mapping.get(text, [])
