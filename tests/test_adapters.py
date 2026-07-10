"""kitty_solting 어댑터 테스트."""

from shortform_editor import editplan
from shortform_editor.adapters import kitty_solting


def test_passthrough_editplan_shape():
    raw = {
        "source": [{"id": "v1", "path": "/a.mp4"}],
        "sections": [{"role": "hook",
                      "clips": [{"source_id": "v1", "start": 0, "end": 2}]}],
    }
    ep = kitty_solting.to_editplan(raw)
    assert ep.sections[0].role == "hook"
    assert editplan.validate(ep) == []


def test_flat_plan_with_korean_roles_and_in_out():
    raw = {
        "sources": [{"id": "v1", "path": "/a.mp4"}],
        "plan": [
            {"section": "후킹", "source": "v1", "in": 10, "out": 13},
            {"section": "유지", "source": "v1", "in": 13, "out": 20},
            {"section": "main", "source": "v1", "start": 40, "end": 50},
            {"section": "CTA", "source": "v1", "in": 55, "out": 58},
        ],
    }
    ep = kitty_solting.to_editplan(raw)
    assert [s.role for s in ep.sections] == ["hook", "retention", "main", "cta"]
    assert ep.sections[0].clips[0].start == 10
    assert editplan.validate(ep) == []


def test_flat_plan_single_source_omitted_source_field():
    raw = {
        "sources": [{"id": "only", "path": "/a.mp4"}],
        "clips": [
            {"role": "hook", "start": 0, "end": 3},
            {"role": "main", "start": 3, "end": 10},
        ],
    }
    ep = kitty_solting.to_editplan(raw)
    assert all(c.source_id == "only"
               for s in ep.sections for c in s.clips)


def test_groups_multiple_clips_into_same_section():
    raw = {
        "sources": [{"id": "v1", "path": "/a.mp4"}],
        "timeline": [
            {"section": "main", "source": "v1", "start": 0, "end": 2},
            {"section": "main", "source": "v1", "start": 5, "end": 7},
        ],
    }
    ep = kitty_solting.to_editplan(raw)
    assert len(ep.sections) == 1
    assert len(ep.sections[0].clips) == 2
