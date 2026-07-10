"""EditPlan — 편집기의 입력 계약(contract).

기획자(키티조정기·숏폼솔팅기)의 산출물은 어댑터를 거쳐 이 모델로 정규화된다.
편집기 본체(timeline/capcut_draft)는 오직 EditPlan에만 의존하므로, 기획자 산출물
형식이 바뀌어도 어댑터만 고치면 된다.

시간 단위는 모두 '초(float)'다. (CapCut draft로 넘어갈 때 마이크로초로 변환)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# 후킹 → 유지 → Main → CTA. 숏폼 마케팅 구조의 표준 순서.
ROLES = ("hook", "retention", "main", "cta")

ROLE_LABELS_KO = {
    "hook": "후킹",
    "retention": "유지",
    "main": "메인",
    "cta": "CTA",
}

# 트렌드 기반 기본 구성 비율(폴백 기획기용).
# 숏폼은 첫 2~3초의 후킹과 마지막 CTA가 성패를 좌우한다는 통념을 반영한 휴리스틱.
# 기획자 산출물이 있으면 이 값은 쓰이지 않는다.
DEFAULT_RATIOS = {
    "hook": 0.12,
    "retention": 0.23,
    "main": 0.50,
    "cta": 0.15,
}


class EditPlanError(ValueError):
    """EditPlan 검증 실패."""


@dataclass
class SourceClip:
    id: str
    path: str


@dataclass
class PlanClip:
    """원본(source_id) 안에서 잘라 쓸 구간 [start, end] (초)."""

    source_id: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Section:
    role: str
    clips: list[PlanClip] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return sum(c.duration for c in self.clips)


@dataclass
class EditPlan:
    sources: list[SourceClip] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    # "auto": 도구가 STT로 자막 자동 생성. 또는 미리 만든 자막 리스트.
    captions: object = "auto"

    def source_ids(self) -> set[str]:
        return {s.id for s in self.sources}

    def ordered_sections(self) -> list[Section]:
        """ROLES 표준 순서로 정렬된 섹션."""
        order = {role: i for i, role in enumerate(ROLES)}
        return sorted(self.sections, key=lambda s: order.get(s.role, len(ROLES)))


# ---------------------------------------------------------------------------
# 직렬화
# ---------------------------------------------------------------------------

def from_dict(data: dict) -> EditPlan:
    """dict(JSON) → EditPlan."""
    sources = [SourceClip(id=str(s["id"]), path=str(s["path"]))
               for s in data.get("source", data.get("sources", []))]
    sections = []
    for sec in data.get("sections", []):
        clips = [PlanClip(source_id=str(c["source_id"]),
                          start=float(c["start"]),
                          end=float(c["end"]))
                 for c in sec.get("clips", [])]
        sections.append(Section(role=str(sec["role"]).lower(), clips=clips))
    captions = data.get("captions", "auto")
    return EditPlan(sources=sources, sections=sections, captions=captions)


def to_dict(plan: EditPlan) -> dict:
    """EditPlan → dict(JSON)."""
    return {
        "source": [{"id": s.id, "path": s.path} for s in plan.sources],
        "sections": [
            {
                "role": sec.role,
                "clips": [
                    {"source_id": c.source_id, "start": c.start, "end": c.end}
                    for c in sec.clips
                ],
            }
            for sec in plan.sections
        ],
        "captions": plan.captions,
    }


# ---------------------------------------------------------------------------
# 검증
# ---------------------------------------------------------------------------

def validate(plan: EditPlan) -> list[str]:
    """검증 결과를 오류 메시지 리스트로 반환한다. 빈 리스트면 유효."""
    errors: list[str] = []

    if not plan.sources:
        errors.append("source가 비어 있습니다. 최소 1개의 원본 영상이 필요합니다.")

    ids = [s.id for s in plan.sources]
    if len(ids) != len(set(ids)):
        errors.append("source id가 중복됩니다.")
    for s in plan.sources:
        if not s.path:
            errors.append(f"source '{s.id}'의 path가 비어 있습니다.")

    if not plan.sections:
        errors.append("sections가 비어 있습니다.")

    seen_roles: set[str] = set()
    known_ids = set(ids)
    for sec in plan.sections:
        if sec.role not in ROLES:
            errors.append(f"알 수 없는 role '{sec.role}'. 허용: {', '.join(ROLES)}")
        if sec.role in seen_roles:
            errors.append(f"role '{sec.role}'가 중복됩니다.")
        seen_roles.add(sec.role)
        if not sec.clips:
            errors.append(f"role '{sec.role}' 섹션에 clip이 없습니다.")
        for c in sec.clips:
            if c.source_id not in known_ids:
                errors.append(
                    f"clip이 존재하지 않는 source '{c.source_id}'를 참조합니다.")
            if c.start < 0:
                errors.append(f"clip start가 음수입니다: {c.start}")
            if c.end <= c.start:
                errors.append(
                    f"clip 구간이 잘못되었습니다(end<=start): {c.start}~{c.end}")

    if plan.captions != "auto" and not isinstance(plan.captions, list):
        errors.append("captions는 'auto' 또는 자막 리스트여야 합니다.")

    return errors


def ensure_valid(plan: EditPlan) -> EditPlan:
    """검증 실패 시 EditPlanError를 던지고, 통과하면 그대로 반환."""
    errs = validate(plan)
    if errs:
        raise EditPlanError("EditPlan 검증 실패:\n- " + "\n- ".join(errs))
    return plan


# ---------------------------------------------------------------------------
# 폴백 기획기 (기획자 산출물이 없을 때)
# ---------------------------------------------------------------------------

def fallback_plan(
    sources: list[SourceClip],
    durations: dict[str, float],
    ratios: Optional[dict[str, float]] = None,
) -> EditPlan:
    """기획안이 없을 때 후킹/유지/Main/CTA 초안을 만든다.

    - 원본 1개: 길이를 ratios 비율로 4구간 순차 분할.
    - 원본 여러 개: 각 클립을 역할에 배치(첫 클립=후킹, 마지막=CTA, 중간=유지/메인).

    durations: source_id -> 길이(초).
    """
    ratios = ratios or DEFAULT_RATIOS
    if not sources:
        raise EditPlanError("폴백 기획: source가 비어 있습니다.")

    if len(sources) == 1:
        return _single_source_plan(sources[0], durations[sources[0].id], ratios)
    return _multi_source_plan(sources, durations)


def _single_source_plan(src: SourceClip, total: float,
                        ratios: dict[str, float]) -> EditPlan:
    sections: list[Section] = []
    cursor = 0.0
    total_ratio = sum(ratios[r] for r in ROLES)
    for i, role in enumerate(ROLES):
        if i == len(ROLES) - 1:
            end = total  # 마지막 섹션은 끝까지(반올림 오차 흡수)
        else:
            end = cursor + total * (ratios[role] / total_ratio)
        end = min(end, total)
        if end > cursor:
            sections.append(
                Section(role=role, clips=[PlanClip(src.id, cursor, end)]))
        cursor = end
    return EditPlan(sources=[src], sections=sections, captions="auto")


def _multi_source_plan(sources: list[SourceClip],
                       durations: dict[str, float]) -> EditPlan:
    n = len(sources)
    # 역할별 소스 인덱스 버킷: 첫 클립=후킹, 마지막=CTA, 중간=유지/메인.
    buckets: dict[str, list[int]] = {r: [] for r in ROLES}
    buckets["hook"].append(0)
    buckets["cta"].append(n - 1)
    middle = list(range(1, n - 1))
    if len(middle) == 1:
        # 중간 클립이 하나면 핵심인 메인에 배치.
        buckets["main"] = middle
    elif len(middle) >= 2:
        # 앞 ~1/3은 유지, 나머지는 메인(메인에 더 많이).
        cut = max(1, len(middle) // 3)
        buckets["retention"] = middle[:cut]
        buckets["main"] = middle[cut:]

    sections: list[Section] = []
    for role in ROLES:
        idxs = buckets[role]
        clips = [
            PlanClip(sources[i].id, 0.0, durations[sources[i].id])
            for i in idxs
        ]
        if clips:
            sections.append(Section(role=role, clips=clips))
    return EditPlan(sources=list(sources), sections=sections, captions="auto")
