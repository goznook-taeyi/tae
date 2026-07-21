from app.models import (
    AnalysisResult,
    CheckType,
    SegmentStatus,
    SpellIssue,
    SubtitleSegment,
)


def test_spelling_issues_property_filters():
    seg = SubtitleSegment(
        id="s0",
        start_s=0,
        end_s=3,
        text="테스트",
        issues=[
            SpellIssue(token="좋내요", suggestion="좋네요", check_type=CheckType.SPELLING),
            SpellIssue(token="안녕 하세요", suggestion="안녕하세요", check_type=CheckType.SPACING),
        ],
    )
    assert len(seg.spelling_issues) == 1
    assert seg.spelling_issues[0].suggestion == "좋네요"


def test_analysis_result_serializes_and_counts():
    result = AnalysisResult(
        video_filename="a.mp4",
        duration_s=6.0,
        segment_count=2,
        segments=[
            SubtitleSegment(id="s0", start_s=0, end_s=3, text="x", status=SegmentStatus.SUSPECT),
            SubtitleSegment(id="s1", start_s=3, end_s=6, text="y", status=SegmentStatus.OK),
        ],
    )
    assert result.suspect_count == 1
    dumped = result.model_dump()
    assert dumped["segments"][0]["status"] == "의심오타"
