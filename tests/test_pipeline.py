"""파이프라인 E2E — 실제 생성 영상 + 콘텐츠 인식 FakeOCR + 스크립트 맞춤법.

실제 영상 디코딩·프레임 그룹핑·안정구간·투표·게이팅 경로를 모두 태우되,
무거운 PaddleOCR 없이 결정적으로 검증한다.
"""

from __future__ import annotations

import os

import cv2
import numpy as np

from app.config import Settings
from app.models import CheckType, SegmentStatus, SpellIssue
from app.ocr import OcrBox, OCREngine
from app.pipeline import analyze_video


class ColorAwareOCR(OCREngine):
    """ROI 밝기로 자막 텍스트를 결정 (어두우면 정상, 밝으면 오타 자막)."""

    def read_boxes(self, image):
        mean = float(np.mean(image))
        text = "안녕하세요 반갑습니다" if mean < 128 else "오늘 날씨가 정말 좋내요"
        h, w = image.shape[:2]
        return [OcrBox(text, 0.95, (5, 5, w - 5, h - 5))]


class TypoChecker:
    def check(self, text: str):
        if "좋내요" in text:
            return [SpellIssue(token="좋내요", suggestion="좋네요", check_type=CheckType.SPELLING)]
        return []


def _make_two_segment_clip(path: str) -> None:
    W, H, FPS, DUR = 320, 240, 10, 4.0
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for i in range(int(DUR * FPS)):
        t = i / FPS
        val = 30 if t < 2.0 else 220
        writer.write(np.full((H, W, 3), val, dtype=np.uint8))
    writer.release()


def test_pipeline_end_to_end(tmp_path):
    clip = str(tmp_path / "clip.mp4")
    _make_two_segment_clip(clip)
    thumb_dir = str(tmp_path / "thumbs")

    settings = Settings(sample_fps=2.0)
    result = analyze_video(clip, ColorAwareOCR(), TypoChecker(), settings, thumb_dir)

    assert result.segment_count == 2
    texts = [s.text for s in result.segments]
    assert any("반갑습니다" in t for t in texts)
    assert any("좋내요" in t for t in texts)

    # 오타 자막은 의심오타, 정상 자막은 정상
    suspect = [s for s in result.segments if s.status == SegmentStatus.SUSPECT]
    assert len(suspect) == 1
    assert suspect[0].spelling_issues[0].suggestion == "좋네요"

    # 썸네일 생성 확인
    for s in result.segments:
        assert s.thumbnail_url
        assert os.path.exists(os.path.join(thumb_dir, s.thumbnail_url))


def test_pipeline_graceful_spellcheck_failure(tmp_path):
    from app.spellcheck import SpellCheckError, SpellChecker

    class AlwaysFail(SpellChecker):
        def check(self, text):
            raise SpellCheckError("boom")

    clip = str(tmp_path / "clip.mp4")
    _make_two_segment_clip(clip)
    result = analyze_video(
        clip, ColorAwareOCR(), AlwaysFail(), Settings(sample_fps=2.0), str(tmp_path / "t")
    )
    # 맞춤법 전부 실패해도 전체 실행은 완료되고 경고가 남음
    assert result.segment_count == 2
    assert result.warnings
    assert all(not s.spellcheck_ok for s in result.segments)
