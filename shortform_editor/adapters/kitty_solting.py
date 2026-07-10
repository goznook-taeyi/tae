"""키티조정기 / 숏폼솔팅기 산출물 → EditPlan 어댑터.

⚠️ 잠정 구현: 실제 산출물 형식을 이 세션에서 확인할 수 없어(다른 저장소/로컬),
가장 흔한 두 가지 형태를 관대하게 받아들이도록 만들었다. 실제 형식을 받으면
아래 매핑만 조정하면 된다.

지원하는 입력 형태
------------------
1) 이미 EditPlan 형태:
   {"source":[{"id","path"}], "sections":[{"role","clips":[{source_id,start,end}]}]}

2) 평평한 컷 리스트(기획자 산출물 가정):
   {
     "sources": [{"id":"v1","path":"..."}],        # 또는 "videos"
     "plan": [                                      # 또는 "timeline"/"clips"/"cuts"
        {"section":"후킹", "source":"v1", "in":10.0, "out":13.0},
        {"section":"main", "source":"v1", "start":40, "end":50},
        ...
     ],
     "captions": "auto"                             # 생략 시 "auto"
   }
"""

from __future__ import annotations

from ..editplan import EditPlan, PlanClip, Section, SourceClip, from_dict

# 역할 별칭(한글/영문/약어) → 표준 role
_ROLE_ALIASES = {
    "hook": "hook", "후킹": "hook", "훅": "hook", "hooking": "hook",
    "retention": "retention", "유지": "retention", "리텐션": "retention",
    "retain": "retention", "keep": "retention",
    "main": "main", "메인": "main", "본론": "main", "body": "main",
    "cta": "cta", "call_to_action": "cta", "행동유도": "cta", "콜투액션": "cta",
    "outro": "cta", "아웃트로": "cta",
}

_START_KEYS = ("start", "in", "from", "begin", "s")
_END_KEYS = ("end", "out", "to", "finish", "e")
_SOURCE_KEYS = ("source_id", "source", "video", "clip_id", "id")
_SECTION_KEYS = ("section", "role", "part", "stage")
_PLAN_KEYS = ("plan", "timeline", "clips", "cuts", "segments", "edits")


def _norm_role(value: str) -> str:
    key = str(value).strip().lower()
    return _ROLE_ALIASES.get(key, key)


def _pick(d: dict, keys) -> object:
    for k in keys:
        if k in d:
            return d[k]
    return None


def to_editplan(raw: dict) -> EditPlan:
    """기획자 산출물(dict) → EditPlan."""
    if not isinstance(raw, dict):
        raise TypeError("기획자 산출물은 dict(JSON 객체)여야 합니다.")

    # 형태 1: 이미 EditPlan
    if "sections" in raw:
        return from_dict(raw)

    # 형태 2: 평평한 컷 리스트
    raw_sources = raw.get("source") or raw.get("sources") or raw.get("videos") or []
    sources = [SourceClip(id=str(s["id"]), path=str(s.get("path", "")))
               for s in raw_sources]
    known_ids = {s.id for s in sources}

    plan_entries = _pick(raw, _PLAN_KEYS) or []

    # 역할 순서를 보존하며 그룹화
    grouped: dict[str, list[PlanClip]] = {}
    order: list[str] = []
    for entry in plan_entries:
        role = _norm_role(_pick(entry, _SECTION_KEYS))
        source_id = _pick(entry, _SOURCE_KEYS)
        # 단일 소스인데 source가 생략된 경우 그 소스로 귀속
        if source_id is None and len(sources) == 1:
            source_id = sources[0].id
        start = _pick(entry, _START_KEYS)
        end = _pick(entry, _END_KEYS)
        if source_id is None or start is None or end is None:
            continue
        clip = PlanClip(source_id=str(source_id),
                        start=float(start), end=float(end))
        if role not in grouped:
            grouped[role] = []
            order.append(role)
        grouped[role].append(clip)

    sections = [Section(role=role, clips=grouped[role]) for role in order]

    # sources가 비어 있으면 plan에서 참조된 id로 채운다(경로는 나중에 주입).
    if not sources:
        ref_ids = []
        for sec in sections:
            for c in sec.clips:
                if c.source_id not in known_ids and c.source_id not in ref_ids:
                    ref_ids.append(c.source_id)
        sources = [SourceClip(id=i, path="") for i in ref_ids]

    captions = raw.get("captions", "auto")
    return EditPlan(sources=sources, sections=sections, captions=captions)
