"""의미적 dedup — 그룹핑의 2차 안전망.

프레임 이미지 유사도 그룹핑(``video.group_segments``)이 얼굴/배경 변화로 같은 자막을
잘못 쪼갠 경우, 투표로 뽑은 합의 텍스트가 인접 세그먼트와 거의 같으면 하나로 병합한다.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from .models import SubtitleSegment

SIMILARITY_THRESHOLD = 0.85


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def merge_adjacent(
    segments: list[SubtitleSegment], threshold: float = SIMILARITY_THRESHOLD
) -> list[SubtitleSegment]:
    """합의 텍스트가 거의 같은 '인접' 세그먼트를 병합한다.

    시간 순서를 유지하며, 인접한 두 세그먼트의 텍스트 유사도가 threshold 이상이면
    시간 구간을 합치고(더 신뢰 높은 텍스트 채택) 프레임 수를 더한다.
    """
    if not segments:
        return []

    merged: list[SubtitleSegment] = [segments[0].model_copy(deep=True)]
    for seg in segments[1:]:
        last = merged[-1]
        if last.text and seg.text and _similar(last.text, seg.text) >= threshold:
            # 더 신뢰 높은 쪽 텍스트 채택
            if seg.ocr_confidence > last.ocr_confidence:
                last.text = seg.text
                last.ocr_confidence = seg.ocr_confidence
                last.vote_agreement = seg.vote_agreement
                last.thumbnail_url = seg.thumbnail_url
            last.end_s = seg.end_s
            last.frame_count += seg.frame_count
            last.has_motion_intro = last.has_motion_intro or seg.has_motion_intro
            last.excluded_sticker_count += seg.excluded_sticker_count
        else:
            merged.append(seg.model_copy(deep=True))
    return merged
