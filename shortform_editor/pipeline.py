"""파이프라인 오케스트레이션.

입력 영상 + (선택)기획안 → 컷 세그먼트 + 자동 자막 → CapCut(Windows) draft 프로젝트.

STT/ffprobe는 주입 가능한 함수로 두어(transcribe_fn/probe_* ) 테스트에서 대체할 수 있다.
"""

from __future__ import annotations

import json
import os
from typing import Callable, Optional, Union

from . import align as align_mod
from . import capcut_draft, captions as captions_mod, editplan as editplan_mod
from . import ffmpeg_utils, installer, timeline
from .adapters import kitty_solting
from .adapters.kitty_solting import ScriptRow
from .editplan import EditPlan, PlanClip, Section, SourceClip


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


def run_scripted(
    video_path: str,
    script_row: ScriptRow,
    *,
    project_name: str = "shortform_auto",
    projects_root: str,
    language: Optional[str] = "ko",
    template_dir: Optional[str] = None,
    install: bool = True,
    copy_media: bool = False,
    backup_dir: Optional[str] = None,
    progress: Optional[Callable[[str], None]] = None,
    transcribe_words_fn: Callable[..., tuple] = captions_mod.transcribe_words,
    probe_duration_fn: Callable[[str], float] = ffmpeg_utils.probe_duration,
    probe_resolution_fn: Callable[[str], tuple] = ffmpeg_utils.probe_resolution,
    running_check: Callable[[], bool] = installer.capcut_running,
) -> str:
    """대본 정렬 모드: 키티조정기 기획안(타임코드 없음) + 촬영본 1개 → CapCut 프로젝트.

    1. STT(단어 타임스탬프)로 촬영본을 전사한다.
    2. 기획안 대본(후킹멘트·main 비트·CTA)과 전사를 정렬해 컷 구간을 찾는다
       (NG 테이크는 마지막 테이크 선택).
    3. 후킹→main→CTA 순으로 컷을 배치하고 자막을 재매핑한다.
       후킹 구간에는 대사 자막 대신 상단질문 타이틀만 얹는다 (편집 문법).
    4. 실제 프로젝트(template_dir)를 프로토타입 삼아 draft를 생성하고,
       install=True면 root_meta_info.json 등록까지 수행한다(캡컷 종료 필수).
    """
    # --- 템플릿(실제 프로젝트) 확보 ---
    template = None
    scaffold = None
    if template_dir is None:
        candidates = installer.find_template_projects(projects_root)
        candidates = [c for c in candidates
                      if os.path.basename(c) != project_name]
        if candidates:
            template_dir = candidates[0]
    if template_dir:
        _log(progress, f"템플릿 프로젝트: {os.path.basename(template_dir)}")
        template = installer.load_template(template_dir)
        scaffold = template_dir
    else:
        _log(progress, "⚠ 템플릿 프로젝트를 찾지 못했습니다 — 최소 골격으로 생성합니다. "
                       "CapCut에서 열리지 않으면 실제 프로젝트를 템플릿으로 지정하세요.")

    # --- STT (단어 타임스탬프) ---
    _log(progress, f"음성인식(STT) 중: {os.path.basename(video_path)} … "
                   "(최초 실행은 모델 다운로드로 오래 걸릴 수 있음)")
    cues, words = transcribe_words_fn(video_path, "v1", language=language)
    _log(progress, f"전사 완료 — 자막 cue {len(cues)}개, 단어 {len(words)}개")

    # --- 대본 정렬 ---
    units = kitty_solting.script_units(script_row)
    _log(progress, f"대본 {len(units)}개 비트를 전사와 정렬 중…")
    result = align_mod.align_script(words, units)
    for w in result.warnings:
        _log(progress, f"⚠ {w}")
    if not result.clips:
        raise ValueError(
            "대본과 일치하는 발화 구간을 하나도 찾지 못했습니다. "
            "영상과 기획안 행이 맞는지 확인하세요.")
    hit = [c for c in result.clips]
    _log(progress, f"정렬 성공 {len(hit)}/{len(units)} 비트 "
                   f"(평균 유사도 {sum(c.score for c in hit)/len(hit):.2f})")

    # --- EditPlan 구성 (역할 순서 유지, 매칭 순서대로) ---
    src = SourceClip(id="v1", path=video_path)
    grouped: dict[str, list[PlanClip]] = {}
    for clip in result.clips:
        grouped.setdefault(clip.unit.role, []).append(
            PlanClip(source_id="v1", start=clip.start, end=clip.end))
    sections = [Section(role=r, clips=grouped[r])
                for r in ("hook", "retention", "main", "cta") if r in grouped]
    ep = EditPlan(sources=[src], sections=sections, captions="auto")

    segments = timeline.build_segments(ep)
    final_caps = timeline.remap_captions(cues, segments)

    # 후킹 구간에는 대사 자막을 넣지 않는다 (편집 문법 §3-3)
    hook_ranges = [(s.target_start, s.target_end)
                   for s in segments if s.role == "hook"]

    def _in_hook(cap: dict) -> bool:
        mid = (cap["start"] + cap["end"]) / 2
        return any(a <= mid < b for a, b in hook_ranges)

    final_caps = [c for c in final_caps if not _in_hook(c)]

    # 상단질문 타이틀 오버레이 (후킹 구간, 없으면 첫 3초)
    titles = []
    tq = (script_row.top_question or "").strip()
    if tq:
        if hook_ranges:
            t_start, t_end = hook_ranges[0][0], hook_ranges[-1][1]
        else:
            t_start, t_end = 0.0, min(3.0, timeline.total_duration(segments))
        if t_end > t_start:
            titles.append({"start": t_start, "end": t_end, "text": tq})

    _log(progress, f"세그먼트 {len(segments)}개, 자막 {len(final_caps)}개, "
                   f"타이틀 {len(titles)}개 — 총 {timeline.total_duration(segments):.1f}초")

    # --- 캔버스 (입력 비율 그대로) ---
    try:
        canvas = probe_resolution_fn(video_path)
    except Exception:
        canvas = (1080, 1920)
        _log(progress, "해상도 감지 실패 — 1080x1920 기본값 사용")

    durations = {}
    try:
        durations["v1"] = probe_duration_fn(video_path)
    except Exception:
        pass

    _log(progress, "CapCut 프로젝트(draft) 생성 중…")
    draft = capcut_draft.build_draft(
        segments, final_caps, name=project_name, canvas=canvas,
        source_durations=durations or None, template=template, titles=titles)

    out_dir = installer.install_project(
        draft, projects_root, scaffold_dir=scaffold, backup_dir=backup_dir,
        register=install, media_paths=[video_path], copy_media=copy_media,
        running_check=running_check)
    _log(progress, f"완료! 프로젝트 폴더: {out_dir}")
    if install:
        _log(progress, "root_meta_info.json에 등록됨 — CapCut을 열면 목록에 보입니다.")
    return out_dir


def default_projects_root() -> Optional[str]:
    """Windows CapCut 기본 draft 경로 추정."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    candidate = os.path.join(
        local, "CapCut", "User Data", "Projects", "com.lveditor.draft")
    return candidate
