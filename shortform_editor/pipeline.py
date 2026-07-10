"""파이프라인 오케스트레이션.

입력 영상 + (선택)기획안 → 컷 세그먼트 + 자동 자막 → CapCut(Windows) draft 프로젝트.

STT/ffprobe는 주입 가능한 함수로 두어(transcribe_fn/probe_* ) 테스트에서 대체할 수 있다.
"""

from __future__ import annotations

import json
import os
from typing import Callable, Optional, Union

from . import capcut_draft, captions as captions_mod, editplan as editplan_mod
from . import ffmpeg_utils, timeline
from .adapters import kitty_solting
from .editplan import EditPlan, SourceClip


def _log(progress: Optional[Callable[[str], None]], msg: str) -> None:
    if progress:
        progress(msg)


def _resolve_plan(
    plan: Union[EditPlan, dict, str, None],
    inputs: Optional[list],
    probe_duration_fn: Callable[[str], float],
    progress,
) -> EditPlan:
    """plan 인자와 inputs로부터 EditPlan을 확정한다."""
    # 1) 기획안이 주어진 경우
    if isinstance(plan, EditPlan):
        ep = plan
    elif isinstance(plan, dict):
        ep = kitty_solting.to_editplan(plan)
    elif isinstance(plan, str):
        with open(plan, "r", encoding="utf-8") as f:
            ep = kitty_solting.to_editplan(json.load(f))
    else:
        ep = None

    # inputs를 SourceClip으로 정규화
    norm_inputs = _normalize_inputs(inputs)

    if ep is None:
        # 2) 폴백 기획: inputs 길이를 재서 후킹/유지/Main/CTA 초안 생성
        if not norm_inputs:
            raise ValueError("입력 영상이 없습니다. inputs 또는 plan이 필요합니다.")
        _log(progress, "기획안이 없어 폴백 기획(후킹→유지→Main→CTA)을 생성합니다…")
        durations = {s.id: probe_duration_fn(s.path) for s in norm_inputs}
        return editplan_mod.fallback_plan(norm_inputs, durations)

    # 3) 기획안의 source 경로가 비어 있으면 inputs에서 채운다
    if norm_inputs:
        path_by_id = {s.id: s.path for s in norm_inputs}
        for s in ep.sources:
            if not s.path and s.id in path_by_id:
                s.path = path_by_id[s.id]
        # 기획안에 source가 없고 inputs만 있으면 붙여준다
        if not ep.sources:
            ep.sources = norm_inputs
    return ep


def _normalize_inputs(inputs) -> list[SourceClip]:
    if not inputs:
        return []
    out: list[SourceClip] = []
    for i, item in enumerate(inputs):
        if isinstance(item, SourceClip):
            out.append(item)
        elif isinstance(item, (tuple, list)):
            out.append(SourceClip(id=str(item[0]), path=str(item[1])))
        else:  # 경로 문자열
            out.append(SourceClip(id=f"v{i+1}", path=str(item)))
    return out


def run(
    inputs: Optional[list] = None,
    *,
    project_name: str = "shortform_auto",
    projects_root: str,
    plan: Union[EditPlan, dict, str, None] = None,
    language: Optional[str] = None,
    canvas: Optional[tuple[int, int]] = None,
    template: Optional[dict] = None,
    copy_media: bool = False,
    progress: Optional[Callable[[str], None]] = None,
    transcribe_fn: Callable[..., list] = captions_mod.transcribe,
    probe_duration_fn: Callable[[str], float] = ffmpeg_utils.probe_duration,
    probe_resolution_fn: Callable[[str], tuple] = ffmpeg_utils.probe_resolution,
) -> str:
    """전체 파이프라인 실행. 생성된 CapCut 프로젝트 폴더 경로를 반환."""
    _log(progress, "기획안 확정 중…")
    ep = _resolve_plan(plan, inputs, probe_duration_fn, progress)
    errs = editplan_mod.validate(ep)
    if errs:
        raise editplan_mod.EditPlanError(
            "기획안 검증 실패:\n- " + "\n- ".join(errs))

    path_by_id = {s.id: s.path for s in ep.sources}

    # --- 자막 ---
    caption_cues: list[dict] = []
    if ep.captions == "auto":
        for src in ep.sources:
            _log(progress, f"자막 생성(STT): {os.path.basename(src.path)} …")
            caption_cues.extend(
                transcribe_fn(src.path, src.id, language=language))
    elif isinstance(ep.captions, list):
        # 이미 만들어진 자막. source_id가 없으면 첫 소스에 귀속.
        default_sid = ep.sources[0].id if ep.sources else None
        for c in ep.captions:
            cue = dict(c)
            cue.setdefault("source_id", default_sid)
            caption_cues.append(cue)

    # --- 세그먼트 & 자막 재매핑 ---
    _log(progress, "컷 세그먼트 배치 중…")
    segments = timeline.build_segments(ep)
    final_caps = timeline.remap_captions(caption_cues, segments)
    _log(progress, f"세그먼트 {len(segments)}개, 자막 {len(final_caps)}개")

    # --- 캔버스(비율 유지) ---
    if canvas is None:
        canvas = (1080, 1920)
        first_path = segments[0].source_path if segments else ""
        if first_path:
            try:
                canvas = probe_resolution_fn(first_path)
            except Exception:  # 해상도 감지 실패 시 세로 기본값
                _log(progress, "해상도 감지 실패 — 1080x1920 기본값 사용")

    # --- CapCut draft 생성 ---
    _log(progress, "CapCut 프로젝트(draft) 생성 중…")
    durations = {}
    for src in ep.sources:
        try:
            durations[src.id] = probe_duration_fn(src.path)
        except Exception:
            pass
    draft = capcut_draft.build_draft(
        segments, final_caps, name=project_name, canvas=canvas,
        source_durations=durations or None, template=template)

    project_dir = os.path.join(projects_root, project_name)
    meta = capcut_draft.build_meta_info(project_name, project_dir)
    media_paths = [path_by_id[s.id] for s in ep.sources if path_by_id.get(s.id)]
    out_dir = capcut_draft.write_draft_project(
        draft, meta, projects_root, media_paths=media_paths,
        copy_media=copy_media)
    _log(progress, f"완료! 프로젝트 폴더: {out_dir}")
    return out_dir


def default_projects_root() -> Optional[str]:
    """Windows CapCut 기본 draft 경로 추정."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    candidate = os.path.join(
        local, "CapCut", "User Data", "Projects", "com.lveditor.draft")
    return candidate
