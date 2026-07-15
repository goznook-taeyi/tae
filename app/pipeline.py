"""파이프라인 오케스트레이션.

영상 → 프레임 그룹핑 → (무빙)안정구간 → (스티커)박스필터 → OCR·다수결 투표
→ 의미적 dedup → 맞춤법 검사 → 신뢰도 게이팅 → AnalysisResult.
"""

from __future__ import annotations

import os
from typing import Callable

from .config import Settings
from .dedup import merge_adjacent
from .models import (
    AnalysisResult,
    SegmentStatus,
    SubtitleSegment,
)
from .ocr import OCREngine, ocr_frame
from .spellcheck import SpellChecker, SpellCheckError
from .video import (
    compute_persistence_mask,
    group_segments,
    pick_vote_frames,
    read_sampled_frames,
    stable_window,
)
from .vote import majority_vote

ProgressCb = Callable[[float, str], None]


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

    report(0.05, "프레임 추출 중")
    frames, duration, _ = read_sampled_frames(path, settings)

    report(0.15, "스티커(지속성) 마스크 계산 중")
    mask = compute_persistence_mask(frames, settings)

    report(0.2, "자막 세그먼트 그룹핑 중")
    raw_segments = group_segments(frames, settings)

    from .thumbs import save_thumbnail

    segments: list[SubtitleSegment] = []
    n = max(1, len(raw_segments))
    for i, seg in enumerate(raw_segments):
        report(0.2 + 0.55 * (i / n), f"OCR·투표 중 ({i + 1}/{n})")
        window, has_motion, stable_found = stable_window(seg, settings)
        vote_frames = pick_vote_frames(window, settings.votes_per_segment)

        reads = []
        excluded_total = 0
        for vf in vote_frames:
            read, excluded = ocr_frame(engine, vf.roi, mask, settings)
            reads.append(read)
            excluded_total += excluded

        vr = majority_vote(reads)
        if not vr.text.strip():
            continue  # 자막 없는 구간

        seg_id = f"seg-{i:04d}"
        mid = vote_frames[len(vote_frames) // 2]
        thumb = save_thumbnail(mid.roi, thumb_dir, seg_id)

        low_conf = (
            not stable_found
            or vr.agreement < settings.low_confidence_threshold
            or vr.confidence < settings.low_confidence_threshold
        )
        segments.append(
            SubtitleSegment(
                id=seg_id,
                start_s=round(seg.start_s, 3),
                end_s=round(seg.end_s, 3),
                text=vr.text,
                ocr_confidence=round(vr.confidence, 3),
                vote_agreement=round(vr.agreement, 3),
                frame_count=len(seg.frames),
                low_confidence=low_conf,
                has_motion_intro=has_motion,
                excluded_sticker_count=excluded_total,
                thumbnail_url=thumb,
            )
        )

    # 의미적 dedup (그룹핑 과분할 병합)
    segments = merge_adjacent(segments)

    # 맞춤법 검사 + 신뢰도 게이팅
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
