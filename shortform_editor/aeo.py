"""AEO/GEO 퍼블리싱 메타데이터 생성.

숏폼 대본(상단질문·후킹·main·CTA)을 AI 검색(AEO/GEO)에 유리한 퍼블리싱
메타데이터로 바꾼다. AEO 실무 가이드의 핵심 전술을 그대로 코드화한 것:

- 답변 먼저(BLUF): 설명 첫 줄에 자기완결형 '정답' 한 문장.
- FAQ: AI 응답의 60%가 FAQ 구조에서 나온다 → 상단질문을 Q로, 대본을 A로.
- 자기완결형 문장: main 비트를 출처·맥락이 담긴 불릿으로 → AI가 그대로 인용.
- YouTube 챕터·자막·설명: YouTube가 AI 노출과 최고 상관(0.737).
- 브랜드 한 문장 일관성: 모든 영상 설명에 같은 자기소개 → 엔티티 강화.

순수 로직 — FFmpeg/whisper/네트워크 의존이 없어 오프라인에서 테스트된다.
자막(SRT) 자체는 captions.build_srt가 만든다; 이 모듈은 '텍스트 메타데이터'를 맡는다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional

from .align import strip_directions

BEAT_SEP = " / "


# ---------------------------------------------------------------------------
# 브랜드 (전 영상 일관 자기소개 — AEO 최우선 전술)
# ---------------------------------------------------------------------------

@dataclass
class Brand:
    """모든 영상 설명에 동일하게 심는 브랜드 엔티티.

    one_liner는 "우리는 [카테고리]의 [브랜드]로 [대상]의 [문제]를 해결한다" 형태를
    권장한다(사이트·SNS·디렉토리와 완전히 동일한 문장이어야 효과가 있다).
    """

    name: str = ""
    one_liner: str = ""
    site: str = ""
    hashtags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 텍스트 유틸 (순수)
# ---------------------------------------------------------------------------

def beats(text: str) -> list[str]:
    """대본 텍스트를 비트(자기완결 문장) 목록으로. 지문·화자 라벨 제거."""
    out = []
    for chunk in (text or "").split(BEAT_SEP):
        cleaned = strip_directions(chunk)
        if cleaned:
            out.append(cleaned)
    return out


def _oneline(text: str) -> str:
    return " ".join((text or "").split())


def _truncate(text: str, limit: int) -> str:
    text = _oneline(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def as_question(text: str) -> str:
    """FAQ 질문용: 끝에 물음표를 보장한다."""
    text = _oneline(text)
    if not text:
        return text
    return text if text.endswith(("?", "？")) else text + "?"


def format_chapter_time(seconds: float) -> str:
    """YouTube 챕터용 타임스탬프. 0초는 반드시 '0:00'."""
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _hashtagify(token: str) -> str:
    # 공백 제거, 앞의 # 정리
    return "#" + _oneline(token).lstrip("#").replace(" ", "")


# ---------------------------------------------------------------------------
# 메타데이터 빌더
# ---------------------------------------------------------------------------

def build_metadata(
    *,
    top_question: str = "",
    hook: str = "",
    main: str = "",
    cta: str = "",
    brand: Optional[Brand] = None,
    keywords: Optional[list[str]] = None,
    hashtags: Optional[list[str]] = None,
    chapters: Optional[list[dict]] = None,
    extra_faq: Optional[list[dict]] = None,
    title_limit: int = 70,
) -> dict:
    """대본 필드 → AEO 퍼블리싱 메타데이터 dict.

    chapters: [{"label": str, "start": float(초)}] (선택). YouTube 챕터로 렌더.
    extra_faq: [{"q","a"}] 추가 FAQ(선택). 근거 있는 것만 넣을 것.
    반환 키: title, bluf, description, faq, hashtags, keywords, chapters.
    """
    hook_beats = beats(hook)
    main_beats = beats(main)
    cta_beats = beats(cta)

    q = _oneline(top_question)
    # 제목: 상단질문 우선(질문형이 AEO에 유리), 없으면 첫 후킹 비트.
    title_src = q or (hook_beats[0] if hook_beats else (main_beats[0] if main_beats else ""))
    title = _truncate(title_src, title_limit)

    # BLUF 정답: 첫 main 비트(자기완결). 없으면 첫 후킹.
    bluf = main_beats[0] if main_beats else (hook_beats[0] if hook_beats else "")

    # 해시태그
    tags = list(hashtags or [])
    if not tags:
        tags = [_hashtagify(k) for k in (keywords or [])]
    if brand and brand.hashtags:
        for h in brand.hashtags:
            ht = _hashtagify(h)
            if ht not in tags:
                tags.append(ht)

    # 설명(YouTube 등): 답변 먼저 → 근거 불릿 → 브랜드 → CTA → 챕터 → 태그
    lines: list[str] = []
    if bluf:
        lines.append(bluf)
    supporting = main_beats[1:] if len(main_beats) > 1 else []
    if supporting:
        lines.append("")
        lines.extend(f"• {b}" for b in supporting)
    if brand and brand.one_liner:
        lines.append("")
        lines.append(_oneline(brand.one_liner))
    if cta_beats:
        lines.append("")
        lines.append(" ".join(cta_beats))
    if chapters:
        lines.append("")
        lines.append("타임스탬프")
        for ch in chapters:
            lines.append(f"{format_chapter_time(ch['start'])} {_oneline(ch.get('label', ''))}".rstrip())
    if tags:
        lines.append("")
        lines.append(" ".join(tags))
    description = "\n".join(lines).strip()

    # FAQ: 상단질문을 Q로, BLUF+보강을 A로 (자기완결·근거형)
    faq: list[dict] = []
    if q:
        answer = bluf
        if supporting:
            answer = f"{bluf} " + " ".join(supporting[:2])
        faq.append({"q": as_question(q), "a": _oneline(answer)})
    for item in (extra_faq or []):
        if item.get("q") and item.get("a"):
            faq.append({"q": as_question(item["q"]), "a": _oneline(item["a"])})

    return {
        "title": title,
        "bluf": bluf,
        "description": description,
        "faq": faq,
        "hashtags": tags,
        "keywords": list(keywords or []),
        "chapters": chapters or [],
    }


def chapters_from_sections(sections: list[dict]) -> list[dict]:
    """편집 섹션 경계 → YouTube 챕터.

    sections: [{"role": "hook"/"main"/"cta", "start": 초}] (최종 타임라인 기준).
    역할을 한국어 라벨로 바꾸고 첫 챕터는 0초로 강제한다(YouTube 규칙).
    """
    label = {"hook": "후킹", "retention": "유지", "main": "핵심", "cta": "마무리"}
    out: list[dict] = []
    for i, sec in enumerate(sorted(sections, key=lambda s: s["start"])):
        start = 0.0 if i == 0 else float(sec["start"])
        out.append({"label": label.get(sec["role"], sec["role"]), "start": start})
    return out


def faq_markdown(faq: list[dict]) -> str:
    """FAQ dict 목록 → 사이트에 붙일 수 있는 마크다운(질문형 H3 + 답변)."""
    blocks = []
    for item in faq:
        blocks.append(f"### {item['q']}\n\n{item['a']}\n")
    return "\n".join(blocks)


def faq_jsonld(faq: list[dict]) -> dict:
    """FAQ → schema.org FAQPage JSON-LD (사이트 삽입용).

    구글 상위 답변의 73%가 스키마 사용 → FAQ 스키마는 AEO의 기본기.
    """
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["q"],
                "acceptedAnswer": {"@type": "Answer", "text": item["a"]},
            }
            for item in faq
        ],
    }


# ---------------------------------------------------------------------------
# 파일 기록 (IO)
# ---------------------------------------------------------------------------

def write_metadata(meta: dict, out_dir: str, name: str = "aeo") -> dict:
    """메타데이터를 프로젝트 폴더에 기록한다.

    - {name}_aeo.json      : 전체 메타데이터
    - {name}_publish.txt   : 제목 + 설명(그대로 복붙용)
    - {name}_faq.md        : FAQ 마크다운(사이트·블로그 삽입용)
    - {name}_faq.jsonld    : FAQPage JSON-LD(스키마 삽입용)
    반환: 파일 경로 dict.
    """
    os.makedirs(out_dir, exist_ok=True)
    paths: dict[str, str] = {}

    p = os.path.join(out_dir, f"{name}_aeo.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    paths["json"] = p

    p = os.path.join(out_dir, f"{name}_publish.txt")
    with open(p, "w", encoding="utf-8") as f:
        f.write(f"[제목]\n{meta['title']}\n\n[설명]\n{meta['description']}\n")
    paths["publish"] = p

    if meta.get("faq"):
        p = os.path.join(out_dir, f"{name}_faq.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(faq_markdown(meta["faq"]))
        paths["faq_md"] = p

        p = os.path.join(out_dir, f"{name}_faq.jsonld")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(faq_jsonld(meta["faq"]), f, ensure_ascii=False, indent=2)
        paths["faq_jsonld"] = p

    return paths
