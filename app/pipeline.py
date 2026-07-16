"""파이프라인 오케스트레이션.

두 가지 그룹핑 모드:
- image: ROI 이미지 유사도로 그룹핑 후 세그먼트당 K프레임 OCR·투표 (정지 배경에 빠름)
- text : 프레임마다 OCR 후 같은 텍스트끼리 병합 (움직이는 배경 위 자막에 강함)

공통 꼬리: 다수결 투표 → 의미적 dedup → 맞춤법 검사 → 신뢰도 게이팅 → AnalysisResult.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable

import numpy as np

from .config import Settings
from .dedup import merge_adjacent
from .models import AnalysisResult, SegmentStatus, SubtitleSegment
from .ocr import OCREngine, ocr_frame
from .spellcheck import SpellChecker, SpellCheckError
from .video import (
    SampledFrame,
    compute_persistence_mask,
    detect_subtitle_band,
    group_segments,
    pick_vote_frames,
    read_sampled_frames,
    stable_window,
)
from .vote import OcrRead, majority_vote, normalize_text

ProgressCb = Callable[[float, str], None]


@dataclass
class _SegData:
    """모드 무관 세그먼트 중간 표현 (투표 재료 + 타이밍)."""

    start_s: float
    end_s: float
    frame_count: int
    reads: list[OcrRead]
    thumb_roi: np.ndarray
    has_motion: bool = False
    stable_found: bool = True
    excluded: int = 0


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _build_image_mode(frames, mask, engine, settings) -> list[_SegData]:
    out: list[_SegData] = []
    for seg in group_segments(frames, settings):
        window, has_motion, stable_found = stable_window(seg, settings)
        vote_frames = pick_vote_frames(window, settings.votes_per_segment)
        reads: list[OcrRead] = []
        excluded = 0
        for vf in vote_frames:
            r, e = ocr_frame(engine, vf.roi, mask, settings)
            reads.append(r)
            excluded += e
        mid = vote_frames[len(vote_frames) // 2]
        out.append(
            _SegData(seg.start_s, seg.end_s, len(seg.frames), reads, mid.roi,
                     has_motion, stable_found, excluded)
        )
    return out


def _build_text_mode(frames: list[SampledFrame], mask, engine, settings) -> list[_SegData]:
    """프레임마다 OCR한 뒤, 연속 프레임의 텍스트가 유사하면 하나의 자막으로 병합."""
    reads: list[OcrRead] = []
    excls: list[int] = []
    for f in frames:
        r, e = ocr_frame(engine, f.roi, mask, settings)
        reads.append(r)
        excls.append(e)

    out: list[_SegData] = []
    cur_idxs: list[int] = []
    cur_repr = ""

    def flush():
        if not cur_idxs:
            return
        i0, i1 = cur_idxs[0], cur_idxs[-1]
        mid = frames[cur_idxs[len(cur_idxs) // 2]]
        out.append(
            _SegData(
                start_s=frames[i0].timestamp_s,
                end_s=frames[i1].timestamp_s,
                frame_count=len(cur_idxs),
                reads=[reads[j] for j in cur_idxs],
                thumb_roi=mid.roi,
                has_motion=False,
                stable_found=True,
                excluded=sum(excls[j] for j in cur_idxs),
            )
        )

    for i in range(len(frames)):
        t = normalize_text(reads[i].text)
        if not t:  # 빈 OCR = 자막 없는 구간 → 경계
            flush()
            cur_idxs, cur_repr = [], ""
            continue
        if cur_idxs and _similar(t, cur_repr) >= settings.text_group_threshold:
            cur_idxs.append(i)
        else:
            flush()
            cur_idxs, cur_repr = [i], t
    flush()
    return out


def analyze_video(
    path: str,
    engine: OCREngine,
    checker: SpellChecker,
    settings: Settings,
    thumb_dir: str,
    progress_cb: ProgressCb | None = None,
) -> AnalysisResult:
    def report(p: float, msg: str) -> None:
        if progress_cb:
            progress_cb(p, msg)

    if settings.roi_auto:
        report(0.02, "자막 위치 자동 감지 중")
        top, bottom = detect_subtitle_band(path, engine, settings)
        settings = settings.model_copy(
            update={"roi_preset": "custom", "roi_top_frac": top, "roi_bottom_frac": bottom}
        )

    report(0.05, "프레임 추출 중")
    frames, duration, _ = read_sampled_frames(path, settings)

    report(0.15, "스티커(지속성) 마스크 계산 중")
    mask = compute_persistence_mask(frames, settings)

    mode = settings.grouping_mode
    report(0.2, f"OCR·그룹핑 중 ({mode} 모드)")
    if mode == "text":
        seg_datas = _build_text_mode(frames, mask, engine, settings)
    else:
        seg_datas = _build_image_mode(frames, mask, engine, settings)

    from .thumbs import save_thumbnail

    segments: list[SubtitleSegment] = []
    for i, sd in enumerate(seg_datas):
        vr = majority_vote(sd.reads)
        if not vr.text.strip():
            continue
        seg_id = f"seg-{i:04d}"
        thumb = save_thumbnail(sd.thumb_roi, thumb_dir, seg_id)
        low_conf = (
            not sd.stable_found
            or vr.agreement < settings.low_confidence_threshold
            or vr.confidence < settings.low_confidence_threshold
        )
        segments.append(
            SubtitleSegment(
                id=seg_id,
                start_s=round(sd.start_s, 3),
                end_s=round(sd.end_s, 3),
                text=vr.text,
                ocr_confidence=round(vr.confidence, 3),
                vote_agreement=round(vr.agreement, 3),
                frame_count=sd.frame_count,
                low_confidence=low_conf,
                has_motion_intro=sd.has_motion,
                excluded_sticker_count=sd.excluded,
                thumbnail_url=thumb,
            )
        )

    segments = merge_adjacent(segments)

    report(0.8, "맞춤법 검사 중")
    spell_failures = 0
    for seg in segments:
        try:
            seg.issues = checker.check(seg.text)
        except SpellCheckError as exc:
            seg.spellcheck_ok = False
            seg.spellcheck_error = str(exc)
            spell_failures += 1

        if seg.low_confidence:
            seg.status = SegmentStatus.REVIEW
        elif seg.spelling_issues:
            seg.status = SegmentStatus.SUSPECT
        else:
            seg.status = SegmentStatus.OK

    warnings: list[str] = []
    if spell_failures:
        warnings.append(
            f"맞춤법 검사 일부 실패: {spell_failures}/{len(segments)} 세그먼트 "
            "(hanspell 네트워크/엔드포인트 문제 가능 — OCR 결과는 정상)"
        )

    report(1.0, "완료")
    return AnalysisResult(
        video_filename=os.path.basename(path),
        duration_s=round(duration, 3),
        segment_count=len(segments),
        segments=segments,
        settings_used=settings.model_dump(),
        warnings=warnings,
    )
