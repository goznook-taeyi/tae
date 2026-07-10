"""editplan 모듈 테스트."""

import pytest

from shortform_editor import editplan
from shortform_editor.editplan import (
    EditPlan,
    EditPlanError,
    PlanClip,
    Section,
    SourceClip,
    ROLES,
)


def _valid_plan():
    return EditPlan(
        sources=[SourceClip("v1", "/tmp/a.mp4")],
        sections=[
            Section("hook", [PlanClip("v1", 0.0, 3.0)]),
            Section("retention", [PlanClip("v1", 3.0, 8.0)]),
            Section("main", [PlanClip("v1", 8.0, 20.0)]),
            Section("cta", [PlanClip("v1", 20.0, 25.0)]),
        ],
    )


def test_roundtrip_dict():
    plan = _valid_plan()
    d = editplan.to_dict(plan)
    back = editplan.from_dict(d)
    assert editplan.to_dict(back) == d


def test_from_dict_accepts_source_or_sources_key():
    d = {"sources": [{"id": "v1", "path": "/a.mp4"}],
         "sections": [{"role": "hook", "clips": [
             {"source_id": "v1", "start": 0, "end": 2}]}]}
    plan = editplan.from_dict(d)
    assert plan.sources[0].id == "v1"
    assert plan.sections[0].clips[0].duration == 2


def test_validate_ok():
    assert editplan.validate(_valid_plan()) == []


def test_validate_empty_sources():
    plan = EditPlan(sources=[], sections=[Section("hook", [])])
    errs = editplan.validate(plan)
    assert any("source" in e for e in errs)


def test_validate_unknown_role():
    plan = EditPlan(
        sources=[SourceClip("v1", "/a.mp4")],
        sections=[Section("intro", [PlanClip("v1", 0, 1)])],
    )
    errs = editplan.validate(plan)
    assert any("role" in e for e in errs)


def test_validate_duplicate_role():
    plan = EditPlan(
        sources=[SourceClip("v1", "/a.mp4")],
        sections=[
            Section("hook", [PlanClip("v1", 0, 1)]),
            Section("hook", [PlanClip("v1", 1, 2)]),
        ],
    )
    errs = editplan.validate(plan)
    assert any("중복" in e for e in errs)


def test_validate_bad_range_and_missing_source():
    plan = EditPlan(
        sources=[SourceClip("v1", "/a.mp4")],
        sections=[Section("hook", [PlanClip("ghost", 5, 3)])],
    )
    errs = editplan.validate(plan)
    assert any("존재하지 않는 source" in e for e in errs)
    assert any("end<=start" in e for e in errs)


def test_ensure_valid_raises():
    plan = EditPlan(sources=[], sections=[])
    with pytest.raises(EditPlanError):
        editplan.ensure_valid(plan)


def test_ordered_sections():
    plan = EditPlan(
        sources=[SourceClip("v1", "/a.mp4")],
        sections=[
            Section("cta", [PlanClip("v1", 20, 25)]),
            Section("hook", [PlanClip("v1", 0, 3)]),
        ],
    )
    roles = [s.role for s in plan.ordered_sections()]
    assert roles == ["hook", "cta"]


# --- 폴백 기획기 ---

def test_fallback_single_source_covers_full_duration():
    src = SourceClip("v1", "/a.mp4")
    plan = editplan.fallback_plan([src], {"v1": 30.0})
    assert [s.role for s in plan.sections] == list(ROLES)
    # 구간이 0부터 30까지 빈틈없이 이어져야 함
    clips = [c for s in plan.sections for c in s.clips]
    assert clips[0].start == 0.0
    assert clips[-1].end == pytest.approx(30.0)
    for a, b in zip(clips, clips[1:]):
        assert a.end == pytest.approx(b.start)
    assert editplan.validate(plan) == []


def test_fallback_multi_source_assigns_roles():
    srcs = [SourceClip(f"c{i}", f"/{i}.mp4") for i in range(4)]
    durs = {s.id: 5.0 for s in srcs}
    plan = editplan.fallback_plan(srcs, durs)
    roles = [s.role for s in plan.sections]
    assert roles == list(ROLES)
    # 첫 클립이 후킹, 마지막 클립이 CTA
    assert plan.sections[0].clips[0].source_id == "c0"
    assert plan.sections[-1].clips[0].source_id == "c3"
    assert editplan.validate(plan) == []


def test_fallback_two_sources_still_valid():
    srcs = [SourceClip("a", "/a.mp4"), SourceClip("b", "/b.mp4")]
    plan = editplan.fallback_plan(srcs, {"a": 4.0, "b": 6.0})
    assert editplan.validate(plan) == []
