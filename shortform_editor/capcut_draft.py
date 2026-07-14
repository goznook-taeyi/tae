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

# 컷 경계 오디오 페이드 기본 길이(µs) — 컷마다 30ms 인/아웃 페이드로 팝음 제거
# (video-use Hard Rule 3 이식. 스키마는 실제 CapCut 프로젝트에서 수확한 실물 그대로)
AUDIO_FADE_US = 30_000


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


def _audio_fade_material(mid: str, fade_us: int) -> dict:
    """실측 스키마(0502/0613 프로젝트에서 수확)의 audio_fade material."""
    return {
        "id": mid,
        "type": "audio_fade",
        "fade_type": 0,
        "fade_in_duration": fade_us,
        "fade_out_duration": fade_us,
    }


def _attach_audio_fades(video_segments: list[dict], materials: dict,
                        gen: Callable[[], str], fade_us: int) -> None:
    """모든 비디오 세그먼트에 인/아웃 페이드를 단다.

    프로토타입 복제로 이미 페이드 ref를 가진 세그먼트는 새로 달지 않고
    그 material의 페이드 길이만 fade_us로 맞춘다(중복 방지).
    """
    fades = materials.setdefault("audio_fades", [])
    existing = {m.get("id"): m for m in fades if isinstance(m, dict)}
    for sd in video_segments:
        refs = sd.setdefault("extra_material_refs", [])
        owned = [existing[r] for r in refs if r in existing]
        if owned:
            for m in owned:
                m["fade_in_duration"] = fade_us
                m["fade_out_duration"] = fade_us
            continue
        fade = _audio_fade_material(gen(), fade_us)
        fades.append(fade)
        existing[fade["id"]] = fade
        refs.append(fade["id"])


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
# 프로토타입 복제 (실측 스키마 호환 — 권장 경로)
# ---------------------------------------------------------------------------
# 실제 CapCut(예: 8.9.1/draft v175)의 세그먼트·material은 필드가 각각 50~100개로,
# 최소 골격 생성으로는 열리지 않을 수 있다. 실제 프로젝트(draft_content.json)를
# template으로 받으면 그 안의 진짜 세그먼트/material을 '프로토타입'으로 복제해
# id·시간·경로·텍스트만 바꾼다 → 스키마가 사용자 CapCut 버전과 100% 일치한다.
# 자막의 폰트·스타일·위치도 실제 프로젝트의 것을 그대로 물려받는다.


def _find_material_with_key(materials: dict, mid: str):
    """material id로 (소속 리스트 키, material dict)를 찾는다."""
    for key, lst in materials.items():
        if not isinstance(lst, list):
            continue
        for m in lst:
            if isinstance(m, dict) and m.get("id") == mid:
                return key, m
    return None, None


def _proto_entry(template: dict, seg: dict):
    mats = template.get("materials", {})
    _key, mat = _find_material_with_key(mats, seg.get("material_id", ""))
    if mat is None:
        return None
    extras = []
    for rid in seg.get("extra_material_refs", []):
        key, m = _find_material_with_key(mats, rid)
        if key and m:
            extras.append((key, m))
    return {"segment": seg, "material": mat, "extras": extras}


def _text_style_size(mat: dict) -> float:
    """텍스트 material의 폰트 크기(스타일 중 최대) — 강조자막 판별용."""
    try:
        data = json.loads(mat.get("content") or "")
        sizes = [s.get("size") for s in data.get("styles", [])
                 if isinstance(s, dict)
                 and isinstance(s.get("size"), (int, float))]
        return float(max(sizes)) if sizes else 0.0
    except (ValueError, TypeError):
        return 0.0


def harvest_prototypes(template: Optional[dict],
                       require_text: bool = True) -> Optional[dict]:
    """template(실제 draft dict)에서 비디오/자막/타이틀 프로토타입을 수확한다.

    반환: {"video", "subtitle", "title", "emphasis"} entry dict 또는 None.
    subtitle = material type이 'subtitle'(자동캡션)인 텍스트,
    title = 그 외 텍스트(인용 타이틀 등). 없으면 subtitle로 대신한다.
    emphasis = 비-자막 텍스트가 여러 스타일이면 폰트가 가장 큰 것(강조자막),
    하나뿐이면 title과 동일.

    require_text=False면 텍스트 프로토가 없어도 video만으로 반환한다
    (수정 모드에서 자막 프로토는 다른 프로젝트에서 빌려올 수 있음).
    """
    if not template or not template.get("tracks"):
        return None
    protos: dict[str, dict] = {}
    title_entries: list[dict] = []
    for tr in template["tracks"]:
        segs = tr.get("segments") or []
        if not segs:
            continue
        if tr.get("type") == "video" and "video" not in protos:
            entry = _proto_entry(template, segs[0])
            if entry:
                protos["video"] = entry
        elif tr.get("type") == "text":
            for seg in segs:
                entry = _proto_entry(template, seg)
                if not entry:
                    continue
                if entry["material"].get("type") == "subtitle":
                    protos.setdefault("subtitle", entry)
                else:
                    title_entries.append(entry)
    if title_entries:
        protos["title"] = title_entries[0]
        protos["emphasis"] = max(title_entries, key=lambda e:
                                 _text_style_size(e["material"]))
    if "video" not in protos:
        return None
    has_text = "subtitle" in protos or "title" in protos
    if require_text and not has_text:
        return None
    if has_text:
        protos.setdefault("subtitle", protos.get("title"))
        protos.setdefault("title", protos.get("subtitle"))
        protos.setdefault("emphasis", protos.get("title"))
    return protos


def _clone_extras(entry: dict, materials: dict,
                  gen: Callable[[], str]) -> list[str]:
    """프로토타입의 부속 material들을 복제해 새 id 목록을 돌려준다."""
    refs: list[str] = []
    for key, proto_mat in entry["extras"]:
        clone = copy.deepcopy(proto_mat)
        clone["id"] = gen()
        materials.setdefault(key, [])
        materials[key].append(clone)
        refs.append(clone["id"])
    return refs


def _reset_segment_dynamics(seg: dict) -> None:
    """복제 세그먼트에서 인스턴스 고유 상태(키프레임·그룹)를 비운다."""
    if "group_id" in seg:
        seg["group_id"] = ""
    if "keyframe_refs" in seg:
        seg["keyframe_refs"] = []
    if "common_keyframes" in seg:
        seg["common_keyframes"] = []
    if "raw_segment_id" in seg:
        seg["raw_segment_id"] = ""


def _clone_video_from_proto(entry: dict, materials: dict, seg: Segment,
                            path: str, duration_us: int,
                            width: int, height: int,
                            mat_cache: dict[str, dict],
                            gen: Callable[[], str]) -> dict:
    """실제 비디오 세그먼트를 복제해 새 컷으로 만든다."""
    # 같은 원본 경로의 material은 재사용
    if path in mat_cache:
        mat = mat_cache[path]
    else:
        mat = copy.deepcopy(entry["material"])
        mat["id"] = gen()
        mat["path"] = path
        mat["material_name"] = os.path.basename(path) if path else ""
        mat["duration"] = duration_us
        mat["width"] = width
        mat["height"] = height
        for k in ("local_material_id", "origin_material_id", "material_url"):
            if k in mat:
                mat[k] = ""
        if isinstance(mat.get("crop"), dict):  # 크롭 초기화(입력 비율 그대로)
            mat["crop"] = {
                "lower_left_x": 0.0, "lower_left_y": 1.0,
                "lower_right_x": 1.0, "lower_right_y": 1.0,
                "upper_left_x": 0.0, "upper_left_y": 0.0,
                "upper_right_x": 1.0, "upper_right_y": 0.0,
            }
        materials.setdefault("videos", []).append(mat)
        mat_cache[path] = mat

    sd = copy.deepcopy(entry["segment"])
    sd["id"] = gen()
    sd["material_id"] = mat["id"]
    dur = _us(seg.duration)
    sd["source_timerange"] = {"start": _us(seg.src_start), "duration": dur}
    sd["target_timerange"] = {"start": _us(seg.target_start), "duration": dur}
    sd["speed"] = 1.0
    sd["visible"] = True
    sd["extra_material_refs"] = _clone_extras(entry, materials, gen)
    if isinstance(sd.get("clip"), dict):  # 화면조정(리프레임) 없음 — 원본 그대로
        sd["clip"] = {
            "alpha": 1.0,
            "flip": {"horizontal": False, "vertical": False},
            "rotation": 0.0,
            "scale": {"x": 1.0, "y": 1.0},
            "transform": {"x": 0.0, "y": 0.0},
        }
    _reset_segment_dynamics(sd)
    return sd


def _patch_text_content(content: str, text: str) -> str:
    """실제 rich-text content JSON의 텍스트만 바꾼다(스타일 유지)."""
    try:
        data = json.loads(content)
        data["text"] = text
        for style in data.get("styles", []):
            if isinstance(style, dict) and "range" in style:
                style["range"] = [0, len(text)]
        return json.dumps(data, ensure_ascii=False)
    except (ValueError, TypeError):
        return json.dumps({"text": text,
                           "styles": [{"range": [0, len(text)]}]},
                          ensure_ascii=False)


def _clone_text_from_proto(entry: dict, materials: dict, cap: dict,
                           gen: Callable[[], str]) -> dict:
    """실제 텍스트(자막/타이틀) 세그먼트를 복제해 새 자막으로 만든다."""
    mat = copy.deepcopy(entry["material"])
    mat["id"] = gen()
    text = cap["text"]
    mat["content"] = _patch_text_content(mat.get("content", ""), text)
    for k in ("recognize_text", "base_content"):
        if k in mat:
            mat[k] = ""
    for k in ("words", "current_words"):
        if isinstance(mat.get(k), dict):
            mat[k] = {"start_time": [], "end_time": [], "text": []}
    materials.setdefault("texts", []).append(mat)

    sd = copy.deepcopy(entry["segment"])
    sd["id"] = gen()
    sd["material_id"] = mat["id"]
    start = _us(cap["start"])
    dur = _us(cap["end"] - cap["start"])
    sd["target_timerange"] = {"start": start, "duration": dur}
    if "source_timerange" in sd and isinstance(sd["source_timerange"], dict):
        sd["source_timerange"] = {"start": 0, "duration": dur}
    sd["visible"] = True
    sd["extra_material_refs"] = _clone_extras(entry, materials, gen)
    _reset_segment_dynamics(sd)
    return sd


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
    for key in ("videos", "texts", "audios", "speeds", "canvases",
                "sound_channel_mappings", "vocal_separations",
                "material_animations", "material_colors", "placeholder_infos",
                "effects", "stickers", "transitions", "audio_fades"):
        materials.setdefault(key, [])
        materials[key] = []


def _reset_template_state(base: dict) -> None:
    """template 재사용 시 이전 편집의 잔여 상태(키프레임 등)를 비운다."""
    if isinstance(base.get("keyframes"), dict):
        for k, v in base["keyframes"].items():
            if isinstance(v, list):
                base["keyframes"][k] = []
    if isinstance(base.get("keyframe_graph_list"), list):
        base["keyframe_graph_list"] = []
    if isinstance(base.get("time_marks"), (list, dict)):
        base["time_marks"] = [] if isinstance(base["time_marks"], list) else {}


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
    titles: Optional[list[dict]] = None,
    protos: Optional[dict] = None,
    audio_fade_us: Optional[int] = None,
) -> dict:
    """세그먼트/자막 → CapCut draft dict.

    canvas: (width, height). 입력 비율 유지가 원칙이므로 원본 해상도를 넘기면 된다.
    source_durations: source_id -> 전체 길이(초). 없으면 사용 구간의 최대값으로 추정.
    template: 실제 CapCut draft dict. 있으면 그 안의 실제 세그먼트/material을
        프로토타입으로 복제해 스키마를 사용자 CapCut 버전과 일치시킨다(권장).
    titles: 대사 자막과 별도의 타이틀 오버레이(상단질문 등) [{"start","end","text"}].
    """
    gen = id_gen or _uuid
    canvas_w, canvas_h = canvas
    if protos is None:
        protos = harvest_prototypes(template)
    if protos and (captions or titles) and "subtitle" not in protos:
        raise ValueError("자막 프로토타입이 없습니다 — 자막이 있는 실제 프로젝트를 "
                         "템플릿으로 지정하거나 protos에 subtitle을 채워주세요.")
    base = copy.deepcopy(template) if template else _default_base(canvas_w, canvas_h)
    base.setdefault("materials", {})
    materials = base["materials"]
    _empty_materials_lists(materials)
    if template:
        _reset_template_state(base)
        base["id"] = gen() if id_gen else _uuid()

    # 소스별 전체 길이(초) 추정.
    est_dur: dict[str, float] = {}
    for seg in segments:
        est_dur[seg.source_id] = max(est_dur.get(seg.source_id, 0.0), seg.src_end)
    if source_durations:
        for sid, d in source_durations.items():
            est_dur[sid] = max(est_dur.get(sid, 0.0), d)

    video_track_segments = []
    text_track_segments = []
    title_track_segments = []

    if protos:
        # --- 프로토타입 복제 경로 (실측 스키마 호환) ---
        mat_cache: dict[str, dict] = {}
        for seg in segments:
            dur_us = _us(est_dur.get(seg.source_id, seg.src_end))
            video_track_segments.append(_clone_video_from_proto(
                protos["video"], materials, seg, seg.source_path,
                dur_us, canvas_w, canvas_h, mat_cache, gen))
        for cap in captions:
            proto = protos["subtitle"]
            if cap.get("kind") == "emph":
                proto = protos.get("emphasis") or proto
            text_track_segments.append(_clone_text_from_proto(
                proto, materials, cap, gen))
        for cap in (titles or []):
            title_track_segments.append(_clone_text_from_proto(
                protos["title"], materials, cap, gen))
    else:
        # --- 최소 골격 경로 (template 없음 — 테스트/폴백) ---
        video_mat_id: dict[str, str] = {}
        for seg in segments:
            if seg.source_id in video_mat_id:
                continue
            mid = gen()
            video_mat_id[seg.source_id] = mid
            materials["videos"].append(_video_material(
                mid, seg.source_path, _us(est_dur.get(seg.source_id, seg.src_end)),
                canvas_w, canvas_h))

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

        for cap in captions:
            mid = gen()
            materials["texts"].append(_text_material(mid, cap["text"]))
            text_track_segments.append(_text_segment(gen(), mid, cap))

        for cap in (titles or []):
            mid = gen()
            materials["texts"].append(_text_material(mid, cap["text"]))
            tseg = _text_segment(gen(), mid, cap)
            # 타이틀은 상단에 배치
            tseg["clip"]["transform"]["y"] = 0.6
            title_track_segments.append(tseg)

    if audio_fade_us:
        _attach_audio_fades(video_track_segments, materials, gen,
                            audio_fade_us)

    total_us = max((s["target_timerange"]["start"] + s["target_timerange"]["duration"]
                    for s in video_track_segments), default=0)

    tracks = [{
        "id": gen(), "type": "video", "attribute": 0, "flag": 0,
        "is_default_name": True, "name": "", "segments": video_track_segments,
    }]
    for segs in (text_track_segments, title_track_segments):
        if segs:
            tracks.append({
                "id": gen(), "type": "text", "attribute": 0, "flag": 0,
                "is_default_name": True, "name": "", "segments": segs,
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
