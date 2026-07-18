"""captions 모듈 테스트 (순수 로직)."""

import pytest

from shortform_editor import captions


def test_format_timecode():
    assert captions.format_timecode(0) == "00:00:00,000"
    assert captions.format_timecode(1.5) == "00:00:01,500"
    assert captions.format_timecode(3661.234) == "01:01:01,234"
    assert captions.format_timecode(-2) == "00:00:00,000"


def test_split_cue_short_passthrough():
    cue = {"source_id": "v1", "start": 0.0, "end": 2.0, "text": "짧은 자막"}
    out = captions.split_cue(cue)
    assert len(out) == 1
    assert out[0]["text"] == "짧은 자막"
    assert out[0]["source_id"] == "v1"


def test_split_cue_empty_text():
    assert captions.split_cue({"start": 0, "end": 1, "text": "   "}) == []


def test_split_cue_long_text_splits_and_preserves_bounds():
    long = "이것은 아주 긴 자막 문장 입니다 그래서 여러 줄로 나뉘어야 합니다 확실히"
    cue = {"source_id": "v1", "start": 0.0, "end": 6.0, "text": long}
    out = captions.split_cue(cue, max_chars=10, max_duration=5.0)
    assert len(out) >= 2
    # 각 조각 글자수 상한 준수
    assert all(len(p["text"]) <= 10 for p in out)
    # 시작/끝 경계 보존, 시간 단조 증가
    assert out[0]["start"] == pytest.approx(0.0)
    assert out[-1]["end"] == pytest.approx(6.0)
    for a, b in zip(out, out[1:]):
        assert a["end"] == pytest.approx(b["start"])
        assert b["start"] >= a["start"]


def test_split_cue_by_duration_only():
    cue = {"start": 0.0, "end": 10.0, "text": "가나다"}  # 짧지만 길이 초과
    out = captions.split_cue(cue, max_chars=20, max_duration=4.0)
    assert len(out) >= 1  # 공백 없는 짧은 텍스트는 글자수로는 안 쪼개짐


def test_wrap_forces_break_for_long_word():
    lines = captions._wrap("가나다라마바사아자차카타파", 4)
    assert all(len(ln) <= 4 for ln in lines)
    assert "".join(lines) == "가나다라마바사아자차카타파"


def test_cues_from_segments():
    segs = [
        {"start": 0.0, "end": 1.0, "text": " 안녕 "},
        {"start": 1.0, "end": 2.0, "text": "반가워"},
    ]
    out = captions.cues_from_segments(segs, "v1")
    assert [c["text"] for c in out] == ["안녕", "반가워"]
    assert all(c["source_id"] == "v1" for c in out)


def test_build_srt():
    caps = [
        {"start": 0.0, "end": 1.0, "text": "첫째"},
        {"start": 1.0, "end": 2.5, "text": "둘째"},
    ]
    srt = captions.build_srt(caps)
    assert "1\n00:00:00,000 --> 00:00:01,000\n첫째" in srt
    assert "2\n00:00:01,000 --> 00:00:02,500\n둘째" in srt
