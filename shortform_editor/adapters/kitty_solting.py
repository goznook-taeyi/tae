"""키티조정기 / 숏폼솔팅기 산출물 → 편집기 입력 어댑터.

실측 확정(2026-07-11): 키티조정기의 실제 산출물은 **타임코드가 없는 촬영 대본**이다.
구글시트/`output/_batch_*.json`/`output/_plan.json` 모두 아래 형태:

    {"title": "...", "folderId": "...",
     "headers": ["no","촬영장소","상단질문","후킹멘트(도입부)",
                  "main 내용(구체화된 원장님 답변)","CTA"],
     "rows": [["1","원장실","<상단질문>","<후킹멘트>","<main 대본>","<CTA>"], ...]}

행 하나 = 숏폼 하나. main 대본의 비트는 " / "로 구분되고 "PD:"/"원장:" 화자 라벨과
"(웃음)" 지문이 섞여 있다. 타임코드가 없으므로 컷 구간은 `align` 모듈이
STT 전사와 대본을 정렬해 찾는다 (→ `ScriptRow` → `script_units()`).

레거시 지원: 타임코드가 있는 EditPlan/컷 리스트 형태도 계속 받는다(수동 기획용).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from ..align import ScriptUnit, strip_directions
from ..editplan import EditPlan, PlanClip, Section, SourceClip, from_dict

# ---------------------------------------------------------------------------
# 실제 키티조정기 포맷 (타임코드 없는 대본 시트)
# ---------------------------------------------------------------------------

# 헤더 → 필드 매핑(부분 일치, 소문자 비교)
_COLUMN_HINTS = {
    "no": ("no",),
    "place": ("촬영장소", "장소"),
    "top_question": ("상단질문",),
    "hook": ("후킹멘트", "후킹", "도입부"),
    "main": ("main", "메인"),
    "cta": ("cta",),
}

BEAT_SEP = " / "
_MIN_UNIT_CHARS = 8  # 이보다 짧은 비트는 다음 비트에 붙인다(정렬 오탐 방지)


@dataclass
class ScriptRow:
    """기획안 시트의 한 행 = 숏폼 1개의 촬영 대본."""

    no: str = ""
    place: str = ""
    top_question: str = ""
    hook: str = ""
    main: str = ""
    cta: str = ""
    title: str = ""  # 시트 제목 (예: "르디테_2026-06-29_여름트렌드10")

    def summary(self) -> str:
        q = " ".join(self.top_question.split())  # 셀 안 줄바꿈 정리
        return f"{self.no}. {q[:40]}{'…' if len(q) > 40 else ''}"


def is_script_sheet(raw: dict) -> bool:
    """키티조정기 대본 시트 형태({headers, rows})인지 판별."""
    return (isinstance(raw, dict)
            and isinstance(raw.get("rows"), list)
            and isinstance(raw.get("headers"), list))


def _map_columns(headers: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, h in enumerate(headers):
        h_low = str(h).strip().lower()
        for fieldname, hints in _COLUMN_HINTS.items():
            if fieldname in mapping:
                continue
            if any(hint in h_low for hint in hints):
                mapping[fieldname] = idx
                break
    return mapping


def parse_script_rows(raw: dict) -> list[ScriptRow]:
    """{title, headers, rows} → ScriptRow 목록."""
    if not is_script_sheet(raw):
        raise ValueError("키티조정기 대본 시트 형식이 아닙니다 (headers/rows 필요).")
    cols = _map_columns([str(h) for h in raw["headers"]])
    missing = [k for k in ("hook", "main", "cta") if k not in cols]
    if missing:
        raise ValueError(f"기획안 헤더에서 컬럼을 찾지 못했습니다: {missing} "
                         f"(headers={raw['headers']})")
    title = str(raw.get("title", ""))
    rows: list[ScriptRow] = []
    for r in raw["rows"]:
        cells = [str(c) for c in r]

        def cell(fieldname: str) -> str:
            idx = cols.get(fieldname)
            return cells[idx].strip() if idx is not None and idx < len(cells) else ""

        rows.append(ScriptRow(
            no=cell("no"), place=cell("place"), top_question=cell("top_question"),
            hook=cell("hook"), main=cell("main"), cta=cell("cta"), title=title))
    return rows


def parse_script_csv(text: str, title: str = "") -> list[ScriptRow]:
    """키티조정기 로컬 백업 CSV(UTF-8, 6컬럼 헤더) → ScriptRow 목록."""
    reader = csv.reader(io.StringIO(text))
    table = [row for row in reader if any(c.strip() for c in row)]
    if len(table) < 2:
        return []
    return parse_script_rows({"title": title, "headers": table[0], "rows": table[1:]})


def _split_beats(text: str) -> list[str]:
    beats = [strip_directions(b) for b in (text or "").split(BEAT_SEP)]
    beats = [b for b in beats if b.strip()]
    # 너무 짧은 비트는 다음 비트와 합친다(정렬 안정성)
    merged: list[str] = []
    carry = ""
    for b in beats:
        piece = f"{carry} {b}".strip() if carry else b
        if len(piece.replace(" ", "")) < _MIN_UNIT_CHARS:
            carry = piece
        else:
            merged.append(piece)
            carry = ""
    if carry:
        if merged:
            merged[-1] = f"{merged[-1]} {carry}"
        else:
            merged.append(carry)
    return merged


def script_units(row: ScriptRow) -> list[ScriptUnit]:
    """대본 행 → 정렬 단위(ScriptUnit) 목록 (후킹 → main 비트들 → CTA 순)."""
    units: list[ScriptUnit] = []
    for i, beat in enumerate(_split_beats(row.hook), start=1):
        units.append(ScriptUnit(role="hook", text=beat, label=f"hook#{i}"))
    for i, beat in enumerate(_split_beats(row.main), start=1):
        units.append(ScriptUnit(role="main", text=beat, label=f"main#{i}"))
    for i, beat in enumerate(_split_beats(row.cta), start=1):
        units.append(ScriptUnit(role="cta", text=beat, label=f"cta#{i}"))
    if not units:
        raise ValueError(f"기획안 행 {row.no}에서 대본을 추출하지 못했습니다.")
    return units


# ---------------------------------------------------------------------------
# 레거시: 타임코드가 있는 컷 리스트 (수동 기획용으로 유지)
# ---------------------------------------------------------------------------

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

    if is_script_sheet(raw):
        raise ValueError(
            "이 기획안은 타임코드가 없는 대본 시트(키티조정기)입니다. "
            "parse_script_rows()로 행을 고른 뒤 pipeline.run_scripted()를 사용하세요.")

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
