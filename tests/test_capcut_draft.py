"""capcut_draft 빌더 테스트 (순수 로직)."""

import json

import pytest

from shortform_editor import capcut_draft
from shortform_editor.capcut_draft import US, build_draft, sequential_id_gen
from shortform_editor.timeline import Segment


def _segments():
    return [
        Segment("v1", "/a.mp4", 10.0, 13.0, 0.0, "hook"),   # 3s @ 0
        Segment("v1", "/a.mp4", 40.0, 50.0, 3.0, "main"),   # 10s @ 3
        Segment("v1", "/a.mp4", 55.0, 58.0, 13.0, "cta"),   # 3s @ 13
    ]


def test_duration_is_timeline_total():
    d = build_draft(_segments(), [], id_gen=sequential_id_gen())
    assert d["duration"] == 16 * US


def test_single_video_material_for_same_source():
    d = build_draft(_segments(), [], id_gen=sequential_id_gen())
    assert len(d["materials"]["videos"]) == 1
    assert d["materials"]["videos"][0]["path"] == "/a.mp4"


def test_video_segments_are_contiguous_and_use_source_range():
    d = build_draft(_segments(), [], id_gen=sequential_id_gen())
    vtrack = [t for t in d["tracks"] if t["type"] == "video"][0]
    segs = vtrack["segments"]
    assert len(segs) == 3
    # 타임라인 연속성
    assert segs[0]["target_timerange"] == {"start": 0, "duration": 3 * US}
    assert segs[1]["target_timerange"] == {"start": 3 * US, "duration": 10 * US}
    assert segs[2]["target_timerange"]["start"] == 13 * US
    # source 구간 반영
    assert segs[1]["source_timerange"] == {"start": 40 * US, "duration": 10 * US}


def test_text_track_created_per_caption():
    caps = [
        {"start": 0.0, "end": 1.0, "text": "안녕"},
        {"start": 1.0, "end": 2.0, "text": "반가워"},
    ]
    d = build_draft(_segments(), caps, id_gen=sequential_id_gen())
    ttrack = [t for t in d["tracks"] if t["type"] == "text"][0]
    assert len(ttrack["segments"]) == 2
    assert len(d["materials"]["texts"]) == 2
    assert d["materials"]["texts"][0]["text"] == "안녕"
    # 텍스트 material content는 유효 JSON 문자열
    parsed = json.loads(d["materials"]["texts"][0]["content"])
    assert parsed["text"] == "안녕"
    # 자막 타임코드 반영
    assert ttrack["segments"][1]["target_timerange"] == {
        "start": 1 * US, "duration": 1 * US}


def test_no_text_track_when_no_captions():
    d = build_draft(_segments(), [], id_gen=sequential_id_gen())
    assert all(t["type"] != "text" for t in d["tracks"])


def test_each_video_segment_has_support_material_refs():
    d = build_draft(_segments(), [], id_gen=sequential_id_gen())
    vtrack = [t for t in d["tracks"] if t["type"] == "video"][0]
    for seg in vtrack["segments"]:
        # speed/canvas/scm/vocal 4종 참조
        assert len(seg["extra_material_refs"]) == 4
    assert len(d["materials"]["speeds"]) == 3
    assert len(d["materials"]["canvases"]) == 3


def test_template_is_used_as_base():
    template = {
        "materials": {"videos": [{"id": "STALE"}], "texts": []},
        "version": 999999,
        "custom_marker": "keep-me",
        "canvas_config": {"width": 1, "height": 1},
    }
    d = build_draft(_segments(), [], canvas=(1080, 1920),
                    template=template, id_gen=sequential_id_gen())
    # template 고유 필드는 보존
    assert d["custom_marker"] == "keep-me"
    assert d["version"] == 999999
    # 하지만 편집 대상 리스트는 새로 채워짐(STALE 제거)
    assert all(v["id"] != "STALE" for v in d["materials"]["videos"])
    assert d["canvas_config"]["width"] == 1080


def test_multi_source_distinct_materials():
    segs = [
        Segment("a", "/a.mp4", 0, 2, 0, "hook"),
        Segment("b", "/b.mp4", 0, 3, 2, "cta"),
    ]
    d = build_draft(segs, [], id_gen=sequential_id_gen())
    paths = {v["path"] for v in d["materials"]["videos"]}
    assert paths == {"/a.mp4", "/b.mp4"}


def test_build_meta_info():
    meta = capcut_draft.build_meta_info("proj", "C:/x/com.lveditor.draft/proj")
    assert meta["draft_name"] == "proj"
    assert "draft_id" in meta
