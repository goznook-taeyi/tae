"""파이프라인 오케스트레이션.

입력 영상 + (선택)기획안 → 컷 세그먼트 + 자동 자막 → CapCut(Windows) draft 프로젝트.

STT/ffprobe는 주입 가능한 함수로 두어(transcribe_fn/probe_* ) 테스트에서 대체할 수 있다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable, Optional, Union

from . import align as align_mod
from . import autocut as autocut_mod
from . import capcut_draft, captions as captions_mod, editplan as editplan_mod
from . import ffmpeg_utils, installer, timeline
from .adapters import kitty_solting
from .adapters.kitty_solting import ScriptRow
from .editplan import EditPlan, PlanClip, Section, SourceClip


def _log(progress: Optional[Callable[[str], None]], msg: str) -> None:
    if progress:
        progress(msg)


@dataclass
class EditOptions:
    """편집 규칙/제약 — GUI(포맷·무음 강도·목표 길이·전사 태깅)에서 설정한다."""

    fmt: str = "short"                    # short(구조 재배치) | mid(순서 유지) | long(최소 개입)
    max_silence: float = autocut_mod.MAX_SILENCE   # 무음 컷 기준(초)
    target_range: Optional[tuple] = None  # (최소, 최대)초 — 초과 시 저가치 main 컷 탈락
    pinned_hook: Optional[tuple] = None   # 훅으로 고정할 원본 구간 (start, end)
    deleted: list = field(default_factory=list)    # 삭제 지정 [(start, end)]
    must_keep: list = field(default_factory=list)  # 보호 지정 [(start, end)]


@dataclass
class ModifyResult:
    """run_modify 결과 — GUI의 요약 패널/되돌리기/태깅에 쓰인다."""

    project_dir: str
    backup_dir: str = ""
    segments: list = field(default_factory=list)   # [{"role","src_start","src_end","duration","text"}]
    warnings: list = field(default_factory=list)
    sentences: list = field(default_factory=list)  # analyze_only: [{"start","end","text"}]
    analyzed_only: bool = False


def _mid_t(w: dict) -> float:
    return (float(w["start"]) + float(w["end"])) / 2


def _in_ranges(t: float, ranges: list) -> bool:
    return any(a <= t < b for a, b in ranges)


def _overlaps(s: float, e: float, ranges: list) -> bool:
    return any(min(e, b) - max(s, a) > 0 for a, b in ranges)


def _range_text(words: list, s: float, e: float, limit: int = 40) -> str:
    txt = " ".join((w.get("text") or "").strip() for w in words
                   if s <= _mid_t(w) < e)
    txt = " ".join(txt.split())
    return txt[:limit] + ("…" if len(txt) > limit else "")


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


def _compute_edit(
    words: list,
    cues: list,
    script_row: Optional[ScriptRow],
    video_path: str,
    progress: Optional[Callable[[str], None]] = None,
    options: Optional[EditOptions] = None,
):
    """전사 + (선택)기획안 + 옵션 → (segments, 자막, 타이틀, 경고). 컷 계산의 공용 코어.

    포맷 규칙: short=구조 재배치+타이틀, mid=순서 유지, long=무음·NG 컷만.
    마지막에 모든 컷 구간 안의 무음(options.max_silence 이상)을 정밀 트리밍한다.
    """
    opt = options or EditOptions()
    warns: list[str] = []

    # 삭제 지정 구간의 발화는 처음부터 없는 것으로 취급한다
    if opt.deleted:
        n0 = len(words)
        words = [w for w in words if not _in_ranges(_mid_t(w), opt.deleted)]
        _log(progress, f"삭제 지정 {len(opt.deleted)}구간 반영 — "
                       f"단어 {n0 - len(words)}개 제외")

    structured = opt.fmt == "short"

    # --- 1차: 대본-전사 정렬 (기획안이 있고, 롱폼이 아닐 때) ---
    if script_row is not None and opt.fmt != "long":
        units = kitty_solting.script_units(script_row)
        _log(progress, f"대본 {len(units)}개 비트를 전사와 정렬 중…")
        result = align_mod.align_script(words, units)
        matched_ratio = len(result.clips) / max(len(units), 1)
    else:
        units, result = [], align_mod.AlignResult()
        matched_ratio = 0.0
        _log(progress, ("롱폼 — 무음·NG 컷만 적용합니다." if opt.fmt == "long"
                        else "기획안 없음 — 전사 기반 자동컷으로 편집합니다."))

    grouped: dict[str, list[PlanClip]] = {}
    if units and matched_ratio >= 0.5:
        for w in result.warnings:
            _log(progress, f"⚠ {w}")
        _log(progress, f"정렬 성공 {len(result.clips)}/{len(units)} 비트 "
                       f"(평균 유사도 "
                       f"{sum(c.score for c in result.clips)/len(result.clips):.2f})")
        for clip in result.clips:
            grouped.setdefault(clip.unit.role, []).append(
                PlanClip(source_id="v1", start=clip.start, end=clip.end))
    else:
        # --- 2차(폴백): 전사 기반 자동컷 (기획안 없음 또는 즉흥 발화) ---
        if units:
            _log(progress,
                 f"대본과 발화 일치율이 낮습니다({len(result.clips)}/{len(units)} 비트) — "
                 "전사 기반 자동컷으로 전환합니다 (무음·반복 테이크 제거).")
        blocks = autocut_mod.blocks_from_words(words)
        n_raw = len(blocks)
        blocks = autocut_mod.dedupe_takes(blocks)
        if n_raw > len(blocks):
            _log(progress, f"반복 테이크 {n_raw - len(blocks)}개 블록 제거 "
                           f"(마지막 테이크 유지)")
        if not blocks:
            raise ValueError("발화 구간을 찾지 못했습니다. 영상에 음성이 있는지, "
                             "STT 언어 설정이 맞는지 확인하세요.")
        autocut_mod.pad_blocks(blocks)
        if structured:
            roles = autocut_mod.plan_blocks(
                blocks,
                hook_hint=(script_row.hook or script_row.top_question)
                if script_row else "",
                cta_hint=script_row.cta if script_row else "")
        else:
            # 미드폼/롱폼: 순서 유지 — 구조 재배치 없음
            roles = {"main": blocks}
        for role, blks in roles.items():
            grouped[role] = [PlanClip(source_id="v1", start=b.start, end=b.end)
                             for b in blks]
        _log(progress, "자동컷 배치: " + ", ".join(
            f"{r} {len(bs)}컷" for r, bs in roles.items()))

    if not grouped:
        raise ValueError(
            "편집할 구간을 하나도 찾지 못했습니다. "
            "영상과 기획안 행이 맞는지 확인하세요.")

    # --- 훅 고정 (전사 태깅에서 지정, 숏폼 전용) ---
    if opt.pinned_hook and structured:
        ph = (float(opt.pinned_hook[0]), float(opt.pinned_hook[1]))
        for role in list(grouped):
            grouped[role] = [c for c in grouped[role]
                             if not _overlaps(c.start, c.end, [ph])]
        grouped["hook"] = [PlanClip(source_id="v1", start=ph[0], end=ph[1])]
        _log(progress, f"훅 고정: {ph[0]:.1f}~{ph[1]:.1f}초")

    # --- 꼭 살리기 지정: 누락됐으면 main에 추가 ---
    for mk in opt.must_keep:
        s, e = float(mk[0]), float(mk[1])
        covered = any(_overlaps(c.start, c.end, [(s, e)])
                      for cs in grouped.values() for c in cs)
        if not covered:
            grouped.setdefault("main", []).append(
                PlanClip(source_id="v1", start=s, end=e))
            _log(progress, f"꼭 살리기 반영: {s:.1f}~{e:.1f}초")
    if "main" in grouped:
        grouped["main"].sort(key=lambda c: c.start)

    # --- 무음 정밀 트리밍: 컷 구간 안의 무음(기준 이상)을 전부 제거 ---
    n_before = sum(len(cs) for cs in grouped.values())
    for role in list(grouped):
        trimmed: list[PlanClip] = []
        for c in grouped[role]:
            for s, e in autocut_mod.trim_silence(words, c.start, c.end,
                                                 max_silence=opt.max_silence):
                trimmed.append(PlanClip(source_id=c.source_id, start=s, end=e))
        grouped[role] = trimmed
    n_after = sum(len(cs) for cs in grouped.values())
    if n_after > n_before:
        _log(progress, f"무음 정밀 컷: {opt.max_silence}초 이상 무음 제거 "
                       f"({n_before}→{n_after}컷)")

    # --- 목표 길이: 초과분은 저가치 main 컷부터 탈락 (훅/CTA/살리기 보호) ---
    if opt.target_range:
        tmin, tmax = float(opt.target_range[0]), float(opt.target_range[1])
        total = sum(c.duration for cs in grouped.values() for c in cs)
        if total > tmax and grouped.get("main"):
            hints = ""
            if script_row is not None:
                hints = align_mod.normalize(
                    f"{script_row.hook} {script_row.main} {script_row.cta} "
                    f"{script_row.top_question}")

            def _value(c: PlanClip, idx: int, n: int) -> float:
                if _overlaps(c.start, c.end, opt.must_keep):
                    return float("inf")  # 보호
                if hints:
                    ct = align_mod.normalize(_range_text(words, c.start, c.end,
                                                         limit=10_000))
                    if not ct:
                        return 0.0
                    sm = SequenceMatcher(None, ct, hints)
                    match = sum(b.size for b in sm.get_matching_blocks())
                    return match / len(ct)
                # 힌트가 없으면 가운데(양끝에서 먼 컷)부터 버린다
                return -min(idx, n - 1 - idx)

            mains = grouped["main"]
            order = sorted(range(len(mains)),
                           key=lambda i: _value(mains[i], i, len(mains)))
            dropped = set()
            for i in order:
                if total <= tmax:
                    break
                if _value(mains[i], i, len(mains)) == float("inf"):
                    continue
                dropped.add(i)
                total -= mains[i].duration
                _log(progress, f"길이 조절: main 컷 탈락 "
                               f"({mains[i].start:.1f}~{mains[i].end:.1f}초)")
            grouped["main"] = [c for i, c in enumerate(mains)
                               if i not in dropped]
            if not grouped["main"]:
                del grouped["main"]
        total = sum(c.duration for cs in grouped.values() for c in cs)
        if total > tmax:
            warns.append(f"목표 최대 {tmax:.0f}초를 초과합니다 ({total:.0f}초) — "
                         "보호된 컷이 많아 더 줄이지 못했습니다.")
        elif total < tmin:
            warns.append(f"목표 최소 {tmin:.0f}초보다 짧습니다 ({total:.0f}초).")
        for w in warns:
            _log(progress, f"⚠ {w}")

    # --- EditPlan 구성 (역할 순서 유지) ---
    src = SourceClip(id="v1", path=video_path)
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

    # 상단질문 타이틀 오버레이 (숏폼 전용 — 후킹 구간, 없으면 첫 3초)
    titles: list[dict] = []
    tq = ((script_row.top_question or "").strip()
          if script_row and structured else "")
    if tq:
        if hook_ranges:
            t_start, t_end = hook_ranges[0][0], hook_ranges[-1][1]
        else:
            t_start, t_end = 0.0, min(3.0, timeline.total_duration(segments))
        if t_end > t_start:
            titles.append({"start": t_start, "end": t_end, "text": tq})

    _log(progress, f"세그먼트 {len(segments)}개, 자막 {len(final_caps)}개, "
                   f"타이틀 {len(titles)}개 — 총 {timeline.total_duration(segments):.1f}초")
    return segments, final_caps, titles, warns


def run_scripted(
    video_path: str,
    script_row: Optional[ScriptRow] = None,
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
    media_resolver: Optional[Callable[..., str]] = None,
) -> str:
    """자동 가편집: 촬영본 1개 (+선택: 키티조정기 기획안 행) → CapCut 프로젝트.

    1. 영상 입력을 로컬로 확보한다(드라이브 링크 다운로드·SD카드 로컬 복사).
    2. STT(단어 타임스탬프)로 촬영본을 전사한다.
    3. 기획안이 있으면 대본과 전사를 정렬해 컷 구간을 찾는다(NG는 마지막 테이크).
       대본대로 안 말했거나(일치율 낮음) 기획안이 없으면 전사 기반 자동컷
       (무음·반복 테이크 제거)으로 편집한다.
    4. 후킹→main→CTA 순으로 컷을 배치하고 자막을 재매핑한다.
       후킹 구간에는 대사 자막 대신 상단질문 타이틀만 얹는다 (편집 문법).
    5. 실제 프로젝트(template_dir)를 프로토타입 삼아 draft를 생성하고,
       install=True면 root_meta_info.json 등록까지 수행한다(캡컷 종료 필수).
    """
    from . import gdrive
    resolver = media_resolver if media_resolver is not None else gdrive.resolve_media
    video_path = resolver(video_path, progress=progress)
    # --- 템플릿(실제 프로젝트) 확보 ---
    # 프로토타입을 수확할 수 있는(=실제 CapCut이 만든) 프로젝트만 템플릿으로 쓴다.
    # 검증 없이 최소 골격으로 진행하면 CapCut이 "사용할 수 없음"으로 거부하는
    # 프로젝트가 등록되므로, 쓸 만한 템플릿이 없으면 등록 전에 실패한다.
    template = None
    scaffold = None
    candidates = ([template_dir] if template_dir
                  else installer.find_template_projects(projects_root))
    for cand in candidates:
        if not cand or os.path.basename(cand) == project_name:
            continue
        try:
            t = installer.load_template(cand)
        except (OSError, ValueError):
            continue
        if capcut_draft.harvest_prototypes(t):
            template, scaffold = t, cand
            _log(progress, f"템플릿 프로젝트: {os.path.basename(cand)}")
            break
        _log(progress, f"템플릿 후보 건너뜀(프로토타입 없음): "
                       f"{os.path.basename(cand)}")
    if template is None:
        if install:
            raise ValueError(
                "사용할 수 있는 템플릿 프로젝트가 없습니다. CapCut에서 "
                "(영상 1개 + 자막 몇 줄) 프로젝트를 하나 만들어 저장한 뒤 다시 "
                "실행하세요. 템플릿 없이 만든 프로젝트는 CapCut이 열지 못합니다.")
        _log(progress, "⚠ 템플릿 없음 — 최소 골격으로 생성합니다 (등록 안 함).")

    # --- STT (단어 타임스탬프) ---
    _log(progress, f"음성인식(STT) 중: {os.path.basename(video_path)} … "
                   "(최초 실행은 모델 다운로드로 오래 걸릴 수 있음)")
    cues, words = transcribe_words_fn(video_path, "v1", language=language)
    _log(progress, f"전사 완료 — 자막 cue {len(cues)}개, 단어 {len(words)}개")

    segments, final_caps, titles, _warns = _compute_edit(
        words, cues, script_row, video_path, progress)

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


TRANSCRIPT_CACHE = ".autoedit_transcript.json"


def _load_transcript_cache(project_dir: str, src_path: str,
                           language: Optional[str]):
    path = os.path.join(project_dir, TRANSCRIPT_CACHE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            c = json.load(f)
        size = os.path.getsize(src_path) if os.path.isfile(src_path) else 0
        if (c.get("video") == src_path and c.get("size") == size
                and c.get("language") == language):
            return c["cues"], c["words"]
    except (OSError, ValueError, KeyError):
        pass
    return None


def _save_transcript_cache(project_dir: str, src_path: str,
                           language: Optional[str],
                           cues: list, words: list) -> None:
    try:
        size = os.path.getsize(src_path) if os.path.isfile(src_path) else 0
        with open(os.path.join(project_dir, TRANSCRIPT_CACHE), "w",
                  encoding="utf-8") as f:
            json.dump({"video": src_path, "size": size, "language": language,
                       "cues": cues, "words": words}, f, ensure_ascii=False)
    except OSError:
        pass  # 캐시는 최선 노력 — 실패해도 편집엔 지장 없음


def run_modify(
    project_dir: str,
    script_row: Optional[ScriptRow] = None,
    *,
    language: Optional[str] = "ko",
    options: Optional[EditOptions] = None,
    analyze_only: bool = False,
    use_cache: bool = True,
    backup_dir: Optional[str] = None,
    progress: Optional[Callable[[str], None]] = None,
    transcribe_words_fn: Callable[..., tuple] = captions_mod.transcribe_words,
    running_check: Callable[[], bool] = installer.capcut_running,
    require_media: bool = True,
) -> ModifyResult:
    """하이브리드 모드(권장): **캡컷이 만든 기존 프로젝트**를 자동 가편집한다.

    프로젝트 생성·등록은 캡컷이 이미 했으므로(가장 위험했던 단계 삭제),
    이 함수는 프로젝트 '내용'만 바꾼다. root_meta_info.json은 건드리지 않는다.

    analyze_only=True: STT까지만 수행하고 문장 목록을 돌려준다(캐시 저장).
    쓰기가 없으므로 캡컷이 실행 중이어도 된다 — GUI의 [① 분석] 단계.
    전사는 프로젝트 폴더의 캐시(.autoedit_transcript.json)로 재사용된다.
    """
    name = os.path.basename(project_dir)
    draft = installer.load_template(project_dir)
    protos = capcut_draft.harvest_prototypes(draft, require_text=False)
    if not protos:
        raise ValueError(
            f"'{name}' 프로젝트에 영상이 없습니다. 캡컷에서 영상을 올려 "
            "저장한 프로젝트를 선택하세요.")

    videos = draft.get("materials", {}).get("videos", [])
    src_path = next((m.get("path") for m in videos if m.get("path")), None)
    if not src_path:
        raise ValueError(f"'{name}' 프로젝트에서 영상 경로를 찾지 못했습니다.")
    if require_media and not os.path.isfile(src_path):
        raise FileNotFoundError(
            f"프로젝트가 참조하는 영상 파일이 없습니다: {src_path}\n"
            "SD카드/외장 드라이브가 분리되지 않았는지 확인하세요.")

    # --- 전사 (캐시 우선) ---
    cached = _load_transcript_cache(project_dir, src_path, language) \
        if use_cache else None
    if cached:
        cues, words = cached
        _log(progress, "전사 캐시 재사용 (STT 생략)")
    else:
        _log(progress, f"음성인식(STT) 중: {os.path.basename(src_path)} … "
                       "(최초 실행은 모델 다운로드로 오래 걸릴 수 있음)")

        def _prog(r: float) -> None:
            _log(progress, f"[PROG] {r:.2f}")

        try:
            cues, words = transcribe_words_fn(src_path, "v1",
                                              language=language,
                                              progress_fn=_prog)
        except TypeError:  # progress_fn을 모르는 (테스트) 구현
            cues, words = transcribe_words_fn(src_path, "v1",
                                              language=language)
        _log(progress, f"전사 완료 — 자막 cue {len(cues)}개, 단어 {len(words)}개")
        if use_cache:
            _save_transcript_cache(project_dir, src_path, language,
                                   cues, words)

    if analyze_only:
        blocks = autocut_mod.blocks_from_words(words)
        sentences = [{"start": b.start, "end": b.end, "text": b.text}
                     for b in blocks]
        _log(progress, f"분석 완료 — 문장 {len(sentences)}개")
        return ModifyResult(project_dir=project_dir, sentences=sentences,
                            analyzed_only=True)

    # --- 여기부터 쓰기 — 캡컷 완전 종료 필수 ---
    if running_check():
        raise installer.CapCutRunningError(
            "CapCut이 실행 중입니다. 편집할 프로젝트가 캡컷에 열려 있으면 "
            "수정이 유실됩니다 — 캡컷을 완전히 닫고 다시 실행해 주세요.")

    # 자막 프로토가 없으면(막 올린 프로젝트) 다른 프로젝트에서 스타일 차용
    if "subtitle" not in protos:
        donor_root = os.path.dirname(project_dir)
        for cand in installer.find_template_projects(donor_root):
            if os.path.normpath(cand) == os.path.normpath(project_dir):
                continue
            try:
                donor = capcut_draft.harvest_prototypes(
                    installer.load_template(cand))
            except (OSError, ValueError):
                continue
            if donor:
                protos["subtitle"] = donor["subtitle"]
                protos["title"] = donor["title"]
                _log(progress, f"자막 스타일 차용: {os.path.basename(cand)}")
                break
        if "subtitle" not in protos:
            raise ValueError(
                "자막 스타일을 가져올 프로젝트가 없습니다. CapCut에서 자막이 "
                "있는 프로젝트를 하나 만들어 두면 그 스타일을 따라갑니다.")

    segments, final_caps, titles, warns = _compute_edit(
        words, cues, script_row, src_path, progress, options)

    # 캔버스·길이는 프로젝트의 실측값을 그대로 쓴다 (ffprobe 불필요)
    cc = draft.get("canvas_config") or {}
    canvas = (int(cc.get("width") or 1080), int(cc.get("height") or 1920))
    dur_us = max((int(m.get("duration") or 0) for m in videos), default=0)
    durations = {"v1": dur_us / 1_000_000} if dur_us else None

    _log(progress, "프로젝트 내용 재구성 중…")
    new_draft = capcut_draft.build_draft(
        segments, final_caps, name=draft.get("name") or name, canvas=canvas,
        source_durations=durations, template=draft, titles=titles,
        protos=protos)
    new_draft["id"] = draft.get("id", new_draft["id"])  # 프로젝트 정체성 유지

    bdir = installer.update_project_files(new_draft, project_dir,
                                          backup_dir=backup_dir)
    _log(progress, f"완료! 백업: {bdir}")
    _log(progress, "CapCut을 열어 프로젝트를 확인하세요 (등록 과정 없음 — 안전).")

    summary = [{"role": s.role, "src_start": s.src_start,
                "src_end": s.src_end, "duration": s.duration,
                "text": _range_text(words, s.src_start, s.src_end)}
               for s in segments]
    return ModifyResult(project_dir=project_dir, backup_dir=bdir,
                        segments=summary, warnings=warns)


def default_projects_root() -> Optional[str]:
    """Windows CapCut 기본 draft 경로 추정."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    candidate = os.path.join(
        local, "CapCut", "User Data", "Projects", "com.lveditor.draft")
    return candidate
