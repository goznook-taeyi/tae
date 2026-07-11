"""probe_resolution 회전 메타데이터 처리 테스트 (ffprobe 출력을 가짜로 주입)."""

import json

from shortform_editor import ffmpeg_utils


def _patch(monkeypatch, stream: dict):
    monkeypatch.setattr(ffmpeg_utils, "_run",
                        lambda cmd: json.dumps({"streams": [stream]}))


class TestProbeResolution:
    def test_no_rotation(self, monkeypatch):
        _patch(monkeypatch, {"width": 1080, "height": 1920})
        assert ffmpeg_utils.probe_resolution("x.mp4") == (1080, 1920)

    def test_rotate_tag_90_swaps(self, monkeypatch):
        """DJI/폰 세로영상: 1920x1080 + rotate 90 → 표시 기준 1080x1920."""
        _patch(monkeypatch, {"width": 1920, "height": 1080,
                             "tags": {"rotate": "90"}})
        assert ffmpeg_utils.probe_resolution("x.mp4") == (1080, 1920)

    def test_side_data_rotation_minus90_swaps(self, monkeypatch):
        _patch(monkeypatch, {"width": 1920, "height": 1080,
                             "side_data_list": [{"rotation": -90}]})
        assert ffmpeg_utils.probe_resolution("x.mp4") == (1080, 1920)

    def test_rotation_180_keeps(self, monkeypatch):
        _patch(monkeypatch, {"width": 1080, "height": 1920,
                             "side_data_list": [{"rotation": 180}]})
        assert ffmpeg_utils.probe_resolution("x.mp4") == (1080, 1920)
