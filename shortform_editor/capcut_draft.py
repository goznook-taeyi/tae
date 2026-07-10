"""CapCut(Windows) draft 생성기.

최종 세그먼트 목록 + 자막을 CapCut 초안 프로젝트(`draft_content.json`)의 dict로 만든다.
CapCut(=국제판 剪映)의 draft 포맷을 따르며 시간 단위는 마이크로초(us)다.

주의: CapCut draft 스키마는 버전마다 조금씩 다르다. 완전한 호환을 위해서는 실제 사용자
CapCut에서 만든 프로젝트의 `draft_content.json`을 `template`으로 넘겨 base로 삼는 것을
권장한다. template이 있으면 그 구조를 유지한 채 tracks/materials/duration만 채운다.

build_* 함수는 순수(파일 IO 없음). 파일 기록은 write_draft_project()가 담당한다.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import uuid
from typing import Callable, Optional

from .timeline import Segment

US = 1_000_000  # 1초 = 1,000,000 마이크로초


def _uuid() -> str:
    return str(uuid.uuid4()).upper()


def sequential_id_gen(prefix: str = "id") -> Callable[[], str]:
    """테스트용 결정적 id 생성기."""
    counter = {"n": 0}

    def _gen() -> str:
        counter["n"] += 1
        return f"{prefix}-{counter['n']:04d}"

    return _gen


def _us(seconds: float) -> int:
    return int(round(seconds * US))


# ---------------------------------------------------------------------------
# 자재(material) 팩토리
# ---------------------------------------------------------------------------

def _video_material(mid: str, path: str, duration_us: int,
                    width: int, height: int) -> dict:
    return {
        "id": mid,
        "type": "video",
        "path": path,
        "material_name": os.path.basename(path) if path else "",
        "duration": duration_us,
        "width": width,
        "height": height,
        "has_audio": True,
        "volume": 1.0,
    }


def _text_material(mid: str, text: str) -> dict:
    # CapCut은 텍스트를 rich-text JSON 문자열로 보관한다. 최소 스타일만 넣는다.
    content = json.dumps({
        "text": text,
        "styles": [{
            "range": [0, len(text)],
            "size": 8.0,
            "fill": {"content": {"solid": {"color": [1.0, 1.0, 1.0]}}},
            "font": {"path": "", "id": ""},
        }],
    }, ensure_ascii=False)
    return {
        "id": mid,
        "type": "text",
        "content": content,
        "text": text,
        "alignment": 1,
        "letter_spacing": 0,
        "line_spacing": 0.02,
    }


def _support_material(mid: str, mtype: str) -> dict:
    """세그먼트가 참조하는 부속 자재(speed/canvas 등)의 최소 형태."""
    base = {"id": mid, "type": mtype}
    if mtype == "speed":
        base["speed"] = 1.0
        base["mode"] = 0
    elif mtype == "canvas":
        base["color"] = ""
        base["blur"] = 0.0
    elif mtype == "sound_channel_mapping":
        base["audio_channel_mapping"] = 0
        base["is_config_open"] = False
    elif mtype == "vocal_separation":
        base["choice"] = 0
    return base


def _video_segment(seg_id: str, material_id: str, seg: Segment,
                   extra_refs: list[str]) -> dict:
    dur = _us(seg.duration)
    return {
        "id": seg_id,
        "material_id": material_id,
        "source_timerange": {"start": _us(seg.src_start), "duration": dur},
        "target_timerange": {"start": _us(seg.target_start), "duration": dur},
        "speed": 1.0,
        "volume": 1.0,
        "visible": True,
        "enable_adjust": True,
        "extra_material_refs": extra_refs,
        "clip": {
            "alpha": 1.0,
            "flip": {"horizontal": False, "vertical": False},
            "rotation": 0.0,
            "scale": {"x": 1.0, "y": 1.0},
            "transform": {"x": 0.0, "y": 0.0},
        },
    }


def _text_segment(seg_id: str, material_id: str, cap: dict) -> dict:
    start = _us(cap["start"])
    dur = _us(cap["end"] - cap["start"])
    return {
        "id": seg_id,
        "material_id": material_id,
        "target_timerange": {"start": start, "duration": dur},
        "render_index": 14000,
        "visible": True,
        "extra_material_refs": [],
        "clip": {
            "alpha": 1.0,
            "flip": {"horizontal": False, "vertical": False},
            "rotation": 0.0,
            "scale": {"x": 1.0, "y": 1.0},
            # 세로 화면 하단쯤에 배치(정규화 좌표, 0=중앙)
            "transform": {"x": 0.0, "y": -0.75},
        },
    }


# ---------------------------------------------------------------------------
# base(빈 draft) 골격
# ---------------------------------------------------------------------------

def _default_base(canvas_w: int, canvas_h: int) -> dict:
    return {
        "canvas_config": {"width": canvas_w, "height": canvas_h,
                          "ratio": "original"},
        "color_space": 0,
        "duration": 0,
        "fps": 30.0,
        "id": _uuid(),
        "materials": {
            "videos": [],
            "texts": [],
            "audios": [],
            "speeds": [],
            "canvases": [],
            "sound_channel_mappings": [],
            "vocal_separations": [],
            "material_animations": [],
            "stickers": [],
            "effects": [],
            "transitions": [],
        },
        "tracks": [],
        "platform": {"os": "windows", "app_version": ""},
        "version": 360000,
        "new_version": "110.0.0",
        "name": "",
    }


def _empty_materials_lists(materials: dict) -> None:
    """template 재사용 시 편집 대상 material 리스트를 비운다."""
    for key in ("videos", "texts", "speeds", "canvases",
                "sound_channel_mappings", "vocal_separations"):
        materials.setdefault(key, [])
        materials[key] = []


# ---------------------------------------------------------------------------
# 메인 빌더
# ---------------------------------------------------------------------------

def build_draft(
    segments: list[Segment],
    captions: list[dict],
    name: str = "shortform_auto",
    canvas: tuple[int, int] = (1080, 1920),
    source_durations: Optional[dict[str, float]] = None,
    template: Optional[dict] = None,
    id_gen: Optional[Callable[[], str]] = None,
) -> dict:
    """세그먼트/자막 → CapCut draft dict.

    canvas: (width, height). 입력 비율 유지가 원칙이므로 원본 해상도를 넘기면 된다.
    source_durations: source_id -> 전체 길이(초). 없으면 사용 구간의 최대값으로 추정.
    template: 실제 CapCut draft dict. 있으면 base로 삼아 호환성을 높인다.
    """
    gen = id_gen or _uuid
    canvas_w, canvas_h = canvas
    base = copy.deepcopy(template) if template else _default_base(canvas_w, canvas_h)
    base.setdefault("materials", {})
    materials = base["materials"]
    _empty_materials_lists(materials)

    # 소스별 비디오 material(중복 경로는 하나로).
    est_dur: dict[str, float] = {}
    for seg in segments:
        est_dur[seg.source_id] = max(est_dur.get(seg.source_id, 0.0), seg.src_end)
    if source_durations:
        for sid, d in source_durations.items():
            est_dur[sid] = max(est_dur.get(sid, 0.0), d)

    video_mat_id: dict[str, str] = {}
    for seg in segments:
        if seg.source_id in video_mat_id:
            continue
        mid = gen()
        video_mat_id[seg.source_id] = mid
        materials["videos"].append(_video_material(
            mid, seg.source_path, _us(est_dur.get(seg.source_id, seg.src_end)),
            canvas_w, canvas_h))

    # 비디오 트랙 세그먼트 + 부속 자재.
    video_track_segments = []
    for seg in segments:
        speed_id = gen()
        canvas_id = gen()
        scm_id = gen()
        vocal_id = gen()
        materials["speeds"].append(_support_material(speed_id, "speed"))
        materials["canvases"].append(_support_material(canvas_id, "canvas"))
        materials["sound_channel_mappings"].append(
            _support_material(scm_id, "sound_channel_mapping"))
        materials["vocal_separations"].append(
            _support_material(vocal_id, "vocal_separation"))
        video_track_segments.append(_video_segment(
            gen(), video_mat_id[seg.source_id], seg,
            [speed_id, canvas_id, scm_id, vocal_id]))

    # 텍스트(자막) 트랙 세그먼트.
    text_track_segments = []
    for cap in captions:
        mid = gen()
        materials["texts"].append(_text_material(mid, cap["text"]))
        text_track_segments.append(_text_segment(gen(), mid, cap))

    total_us = max((s["target_timerange"]["start"] + s["target_timerange"]["duration"]
                    for s in video_track_segments), default=0)

    tracks = [{
        "id": gen(), "type": "video", "attribute": 0, "flag": 0,
        "is_default_name": True, "name": "", "segments": video_track_segments,
    }]
    if text_track_segments:
        tracks.append({
            "id": gen(), "type": "text", "attribute": 0, "flag": 0,
            "is_default_name": True, "name": "", "segments": text_track_segments,
        })

    base["tracks"] = tracks
    base["duration"] = total_us
    base["name"] = name
    base["canvas_config"] = {"width": canvas_w, "height": canvas_h,
                             "ratio": "original"}
    return base


def build_meta_info(name: str, draft_folder: str, draft_id: Optional[str] = None,
                    create_time: int = 0) -> dict:
    """draft_meta_info.json 내용(간소화)."""
    return {
        "draft_id": (draft_id or _uuid()),
        "draft_name": name,
        "draft_fold_path": draft_folder.replace("/", "\\"),
        "draft_root_path": os.path.dirname(draft_folder).replace("/", "\\"),
        "tm_draft_create": create_time,
        "tm_draft_modified": create_time,
        "draft_removable": True,
    }


# ---------------------------------------------------------------------------
# 파일 기록 (IO)
# ---------------------------------------------------------------------------

def write_draft_project(draft: dict, meta: dict, projects_root: str,
                        media_paths: Optional[list[str]] = None,
                        copy_media: bool = False) -> str:
    """draft/meta를 CapCut 프로젝트 폴더에 기록하고 폴더 경로를 반환.

    projects_root: `.../com.lveditor.draft` 경로.
    copy_media=True면 원본 미디어를 프로젝트 하위 materials 폴더로 복사한다.
    """
    project_dir = os.path.join(projects_root, draft["name"])
    os.makedirs(project_dir, exist_ok=True)

    if copy_media and media_paths:
        materials_dir = os.path.join(project_dir, "materials")
        os.makedirs(materials_dir, exist_ok=True)
        for src in media_paths:
            if src and os.path.exists(src):
                shutil.copy2(src, os.path.join(materials_dir,
                                               os.path.basename(src)))

    with open(os.path.join(project_dir, "draft_content.json"), "w",
              encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
    with open(os.path.join(project_dir, "draft_meta_info.json"), "w",
              encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return project_dir
