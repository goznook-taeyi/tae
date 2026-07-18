"""pipeline 오케스트레이션 테스트 (ffmpeg/whisper 없이 fake 주입)."""

import json
import os

from shortform_editor import pipeline
from shortform_editor.editplan import EditPlan, PlanClip, Section, SourceClip


def _fake_probe_duration(path):
    return 60.0


def _fake_probe_resolution(path):
    return (1080, 1920)


def _fake_transcribe(path, source_id, language=None):
    # 원본 전체에 걸친 자막 두 개
    return [
        {"source_id": source_id, "start": 11.0, "end": 12.0, "text": "후킹자막"},
        {"source_id": source_id, "start": 41.0, "end": 42.0, "text": "메인자막"},
    ]


def _run(tmp_path, **kw):
    return pipeline.run(
        projects_root=str(tmp_path),
        transcribe_fn=_fake_transcribe,
        probe_duration_fn=_fake_probe_duration,
        probe_resolution_fn=_fake_probe_resolution,
        **kw,
    )


def test_run_with_explicit_plan_writes_project(tmp_path):
    plan = EditPlan(
        sources=[SourceClip("v1", "/a.mp4")],
        sections=[
            Section("hook", [PlanClip("v1", 10.0, 13.0)]),
            Section("main", [PlanClip("v1", 40.0, 50.0)]),
            Section("cta", [PlanClip("v1", 55.0, 58.0)]),
        ],
    )
    out = _run(tmp_path, plan=plan, project_name="proj1")
    assert os.path.isdir(out)
    content_path = os.path.join(out, "draft_content.json")
    meta_path = os.path.join(out, "draft_meta_info.json")
    assert os.path.exists(content_path)
    assert os.path.exists(meta_path)

    draft = json.load(open(content_path, encoding="utf-8"))
    # 3개 컷 → 16초 타임라인
    assert draft["duration"] == 16 * 1_000_000
    vtrack = [t for t in draft["tracks"] if t["type"] == "video"][0]
    assert len(vtrack["segments"]) == 3
    # 자막이 STT로 자동 생성되어 텍스트 트랙 존재
    ttrack = [t for t in draft["tracks"] if t["type"] == "text"][0]
    assert len(ttrack["segments"]) == 2


def test_run_fallback_when_no_plan(tmp_path):
    out = _run(tmp_path, inputs=["/only.mp4"], project_name="proj2")
    draft = json.load(open(os.path.join(out, "draft_content.json"),
                           encoding="utf-8"))
    # 폴백은 원본 60초를 4구간으로 → 타임라인 총합 60초
    assert draft["duration"] == 60 * 1_000_000


def test_run_fills_source_path_from_inputs(tmp_path):
    # 기획안엔 경로가 없고 inputs로 경로 주입
    raw_plan = {
        "sources": [{"id": "v1", "path": ""}],
        "plan": [
            {"section": "hook", "source": "v1", "in": 0, "out": 3},
            {"section": "cta", "source": "v1", "in": 3, "out": 6},
        ],
        "captions": "auto",
    }
    out = _run(tmp_path, inputs=[("v1", "/real.mp4")], plan=raw_plan,
               project_name="proj3")
    draft = json.load(open(os.path.join(out, "draft_content.json"),
                           encoding="utf-8"))
    assert draft["materials"]["videos"][0]["path"] == "/real.mp4"


def test_run_plan_from_json_file(tmp_path):
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps({
        "sources": [{"id": "v1", "path": "/a.mp4"}],
        "plan": [{"section": "main", "source": "v1", "start": 0, "end": 5}],
        "captions": "auto",
    }), encoding="utf-8")
    out = _run(tmp_path, plan=str(plan_file), project_name="proj4")
    assert os.path.isdir(out)
