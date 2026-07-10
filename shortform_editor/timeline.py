"""타임라인 구성 (순수 로직).

EditPlan의 섹션(후킹→유지→Main→CTA)을 최종 타임라인 위의 세그먼트 목록으로 펼치고,
원본 시간 기준 자막을 컷·재배치된 최종 타임라인 시간으로 재매핑한다.

시간 단위는 모두 '초(float)'.
"""

from __future__ import annotations

from dataclasses import dataclass

from .editplan import EditPlan


@dataclass
class Segment:
    """최종 타임라인 위에 놓이는 한 컷.

    source_id/path: 어떤 원본에서 왔는지
    src_start/src_end: 원본 안에서 잘라낸 구간(초)
    target_start: 최종 타임라인에서 이 컷이 시작되는 시각(초)
    role: 소속 섹션 역할(hook/retention/main/cta)
    """

    source_id: str
    source_path: str
    src_start: float
    src_end: float
    target_start: float
    role: str

    @property
    def duration(self) -> float:
        return self.src_end - self.src_start

    @property
    def target_end(self) -> float:
        return self.target_start + self.duration


def build_segments(plan: EditPlan) -> list[Segment]:
    """섹션을 순서대로 펼쳐 최종 타임라인 세그먼트 목록을 만든다.

    각 컷은 앞 컷 바로 뒤에 이어 붙는다(무음/불필요 구간은 이미 계획에서 빠졌다는 전제).
    """
    path_by_id = {s.id: s.path for s in plan.sources}
    segments: list[Segment] = []
    cursor = 0.0
    for section in plan.ordered_sections():
        for clip in section.clips:
            seg = Segment(
                source_id=clip.source_id,
                source_path=path_by_id.get(clip.source_id, ""),
                src_start=clip.start,
                src_end=clip.end,
                target_start=cursor,
                role=section.role,
            )
            segments.append(seg)
            cursor += seg.duration
    return segments


def total_duration(segments: list[Segment]) -> float:
    return sum(s.duration for s in segments)


def remap_captions(captions: list[dict], segments: list[Segment]) -> list[dict]:
    """원본 시간 기준 자막을 최종 타임라인 시간으로 재매핑한다.

    caption: {"source_id", "start", "end", "text"} (원본 초 단위).
    컷 경계를 걸치는 자막은 겹치는 각 세그먼트별로 분할되어 여러 개로 나온다.
    잘려나간(어떤 세그먼트에도 안 걸치는) 자막은 버려진다.
    반환: {"start", "end", "text"} 리스트(최종 타임라인 초), 시작 시각 순 정렬.
    """
    out: list[dict] = []
    for cap in captions:
        cap_sid = cap.get("source_id")
        cap_start = float(cap["start"])
        cap_end = float(cap["end"])
        for seg in segments:
            if cap_sid is not None and seg.source_id != cap_sid:
                continue
            ov_start = max(cap_start, seg.src_start)
            ov_end = min(cap_end, seg.src_end)
            if ov_end <= ov_start:
                continue
            final_start = seg.target_start + (ov_start - seg.src_start)
            final_end = seg.target_start + (ov_end - seg.src_start)
            out.append({
                "start": final_start,
                "end": final_end,
                "text": cap["text"],
            })
    out.sort(key=lambda c: c["start"])
    return out
