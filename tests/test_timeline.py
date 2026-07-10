"""timeline 모듈 테스트."""

import pytest

from shortform_editor.editplan import EditPlan, PlanClip, Section, SourceClip
from shortform_editor import timeline


def _plan_single():
    return EditPlan(
        sources=[SourceClip("v1", "/a.mp4")],
        sections=[
            Section("hook", [PlanClip("v1", 10.0, 13.0)]),   # 3s
            Section("main", [PlanClip("v1", 40.0, 50.0)]),   # 10s
            Section("cta", [PlanClip("v1", 55.0, 58.0)]),    # 3s
        ],
    )


def test_build_segments_places_sequentially():
    segs = timeline.build_segments(_plan_single())
    assert [s.role for s in segs] == ["hook", "main", "cta"]
    # target_start가 이어붙어야 함
    assert segs[0].target_start == 0.0
    assert segs[0].target_end == 3.0
    assert segs[1].target_start == 3.0
    assert segs[1].target_end == 13.0
    assert segs[2].target_start == 13.0
    assert timeline.total_duration(segs) == pytest.approx(16.0)


def test_build_segments_resolves_paths_and_multi_source():
    plan = EditPlan(
        sources=[SourceClip("a", "/a.mp4"), SourceClip("b", "/b.mp4")],
        sections=[
            Section("hook", [PlanClip("a", 0, 2)]),
            Section("cta", [PlanClip("b", 1, 4)]),
        ],
    )
    segs = timeline.build_segments(plan)
    assert segs[0].source_path == "/a.mp4"
    assert segs[1].source_path == "/b.mp4"
    assert segs[1].target_start == 2.0


def test_build_segments_orders_by_role_not_input_order():
    plan = EditPlan(
        sources=[SourceClip("v1", "/a.mp4")],
        sections=[
            Section("cta", [PlanClip("v1", 20, 23)]),
            Section("hook", [PlanClip("v1", 0, 2)]),
        ],
    )
    segs = timeline.build_segments(plan)
    assert [s.role for s in segs] == ["hook", "cta"]


def test_remap_caption_inside_single_segment():
    segs = timeline.build_segments(_plan_single())
    # 원본 41~42초 자막 → main 세그먼트(원본40 시작, 타임라인3 시작)
    caps = [{"source_id": "v1", "start": 41.0, "end": 42.0, "text": "안녕"}]
    out = timeline.remap_captions(caps, segs)
    assert len(out) == 1
    assert out[0]["start"] == pytest.approx(4.0)   # 3 + (41-40)
    assert out[0]["end"] == pytest.approx(5.0)
    assert out[0]["text"] == "안녕"


def test_remap_caption_dropped_when_in_cut_region():
    segs = timeline.build_segments(_plan_single())
    # 원본 20~25초는 어떤 컷에도 없음 → 버려짐
    caps = [{"source_id": "v1", "start": 20.0, "end": 25.0, "text": "삭제됨"}]
    assert timeline.remap_captions(caps, segs) == []


def test_remap_caption_splits_across_cut_boundary():
    # 하나의 세그먼트가 원본 10~13, 다음이 원본 40~50.
    segs = timeline.build_segments(_plan_single())
    # 자막이 원본 12~41초에 걸치면 hook(12~13)과 main(40~41)에 각각 매핑
    caps = [{"source_id": "v1", "start": 12.0, "end": 41.0, "text": "걸침"}]
    out = timeline.remap_captions(caps, segs)
    assert len(out) == 2
    # hook 쪽: 12~13 → 타임라인 2~3
    assert out[0]["start"] == pytest.approx(2.0)
    assert out[0]["end"] == pytest.approx(3.0)
    # main 쪽: 40~41 → 타임라인 3~4
    assert out[1]["start"] == pytest.approx(3.0)
    assert out[1]["end"] == pytest.approx(4.0)


def test_remap_respects_source_id():
    plan = EditPlan(
        sources=[SourceClip("a", "/a.mp4"), SourceClip("b", "/b.mp4")],
        sections=[
            Section("hook", [PlanClip("a", 0, 5)]),
            Section("main", [PlanClip("b", 0, 5)]),
        ],
    )
    segs = timeline.build_segments(plan)
    caps = [{"source_id": "b", "start": 1.0, "end": 2.0, "text": "B자막"}]
    out = timeline.remap_captions(caps, segs)
    assert len(out) == 1
    # b는 타임라인 5초부터 시작 → 6~7
    assert out[0]["start"] == pytest.approx(6.0)
