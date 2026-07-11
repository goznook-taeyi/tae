"""대본-전사 정렬 (script ↔ STT transcript alignment).

키티조정기 기획안에는 타임코드가 없다 — 촬영 전 '대본'(후킹멘트·main 비트·CTA)만 있다.
이 모듈은 촬영본의 STT 결과(단어 타임스탬프)와 대본을 유사도 매칭해, 각 대본 단위가
실제로 발화된 원본 구간을 찾아 컷 구간으로 돌려준다.

핵심 규칙 (capcut/EDITING_STYLE.md 반영):
- 같은 대사가 여러 번 촬영(NG 테이크)된 경우 **마지막(최종) 테이크**를 선택한다.
- 컷 경계에 브레스 여유(pad)를 두되, 0.5초 미만 세그먼트는 만들지 않는다.

시간 단위는 '초(float)'. 순수 로직(표준 라이브러리만)이라 STT 없이 테스트된다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

# 매칭으로 인정할 최소 유사도. 대본과 실제 발화는 어미/조사가 달라지므로 느슨하게.
DEFAULT_THRESHOLD = 0.5
# 최고점 대비 이 범위 안의 후보는 '같은 대사의 다른 테이크'로 보고 가장 마지막 것을 고른다.
NEAR_BEST = 0.08
PAD_PRE = 0.12   # 컷 시작 전 여유(초)
PAD_POST = 0.35  # 발화 끝 뒤 브레스 여유(초)
MIN_CLIP_DURATION = 0.5  # 이보다 짧은 컷은 버린다 (EDITING_STYLE §2-2)

_NORM_RE = re.compile(r"[^0-9a-z가-힣]+")
_PAREN_RE = re.compile(r"[\(（][^)）]*[\)）]")  # (웃음) 같은 지문
_SPEAKER_RE = re.compile(r"(?:^|[/\n]\s*)(?:PD|피디|원장|의사|MC|Q|A)\s*[:：]", re.IGNORECASE)


def normalize(text: str) -> str:
    """비교용 정규화: 한글/영문(소문자)/숫자만 남긴다."""
    return _NORM_RE.sub("", (text or "").lower())


def strip_directions(text: str) -> str:
    """지문 '(웃음)'과 화자 라벨 'PD:', '원장:'을 대사에서 제거한다."""
    text = _PAREN_RE.sub(" ", text or "")
    text = _SPEAKER_RE.sub(" ", text)
    return " ".join(text.split())


@dataclass
class ScriptUnit:
    """정렬 대상이 되는 대본 한 조각(비트)."""

    role: str            # hook / main / cta
    text: str            # 발화 대본(지문·화자 라벨 제거 후)
    label: str = ""      # 표시용 (예: "main#2")


@dataclass
class MatchedClip:
    """대본 단위가 원본에서 발화된 것으로 판정된 구간."""

    unit: ScriptUnit
    start: float         # 원본 초 (pad 적용 후)
    end: float
    score: float         # 유사도 0~1
    matched_text: str = ""


@dataclass
class AlignResult:
    clips: list[MatchedClip] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def words_from_cues(cues: list[dict]) -> list[dict]:
    """단어 타임스탬프가 없을 때 cue(문장) 단위 자막을 글자 비율로 쪼개 유사-단어를 만든다."""
    words: list[dict] = []
    for cue in cues:
        text = (cue.get("text") or "").strip()
        if not text:
            continue
        parts = text.split() or [text]
        total = sum(len(p) for p in parts) or 1
        start, end = float(cue["start"]), float(cue["end"])
        dur = max(end - start, 0.0)
        cursor = start
        for i, p in enumerate(parts):
            share = len(p) / total
            w_end = end if i == len(parts) - 1 else cursor + dur * share
            words.append({"start": cursor, "end": w_end, "text": p})
            cursor = w_end
    return words


def align_script(
    words: list[dict],
    units: list[ScriptUnit],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    near_best: float = NEAR_BEST,
    pad_pre: float = PAD_PRE,
    pad_post: float = PAD_POST,
    min_duration: float = MIN_CLIP_DURATION,
) -> AlignResult:
    """대본 단위들을 순서대로 전사(단어 목록)에 매칭해 컷 구간을 찾는다.

    words: [{"start","end","text"}] — 원본 시간순 단어 목록.
    units: 대본 단위(순서 = 촬영/편집 순서 가정).

    각 단위는 이전 단위가 끝난 지점 이후에서만 찾는다(촬영 순서 = 대본 순서 전제).
    같은 대사의 후보(최고점 근처)가 여럿이면 가장 뒤의 것(최종 테이크)을 고른다.
    """
    result = AlignResult()
    norm_words = [normalize(w.get("text", "")) for w in words]
    n = len(words)
    cursor = 0
    prev_end_time: Optional[float] = None

    for unit in units:
        target = normalize(unit.text)
        if not target:
            continue
        best = _find_matches(norm_words, cursor, target, threshold, near_best)
        if not best:
            result.warnings.append(
                f"[{unit.label or unit.role}] 대본과 일치하는 발화를 찾지 못했습니다: "
                f"“{unit.text[:30]}…”")
            continue
        i, j, score = best  # 단어 인덱스 [i, j] (포함), 유사도

        start = max(0.0, float(words[i]["start"]) - pad_pre)
        end = float(words[j]["end"]) + pad_post
        if prev_end_time is not None and start < prev_end_time:
            start = prev_end_time  # 이전 컷과 겹치지 않게
        if end - start < min_duration:
            result.warnings.append(
                f"[{unit.label or unit.role}] 매칭 구간이 {end - start:.2f}초로 너무 짧아 "
                f"버립니다 (최소 {min_duration}초).")
            cursor = j + 1
            continue

        result.clips.append(MatchedClip(
            unit=unit, start=start, end=end, score=score,
            matched_text=" ".join((words[k].get("text") or "").strip()
                                  for k in range(i, j + 1))))
        cursor = j + 1
        prev_end_time = end

    return result


def _find_matches(norm_words: list[str], cursor: int, target: str,
                  threshold: float, near_best: float):
    """cursor 이후에서 target과 가장 잘 맞는 단어 구간을 찾는다.

    반환: (시작 단어 idx, 끝 단어 idx, 점수) 또는 None.
    최고점과 near_best 이내의 후보가 여럿이면 가장 마지막 후보(최종 테이크)를 고른 뒤
    끝 경계를 ±몇 단어 미세조정한다.
    """
    n = len(norm_words)
    tlen = len(target)
    if tlen == 0 or cursor >= n:
        return None

    candidates: list[tuple[int, int, float]] = []  # (i, j, score)
    for i in range(cursor, n):
        if not norm_words[i]:
            continue
        # i에서 시작해 target 길이만큼 단어를 모은 창
        acc = 0
        j = i
        while j < n and acc < tlen:
            acc += len(norm_words[j])
            j += 1
        j = min(j - 1, n - 1)
        window = "".join(norm_words[i:j + 1])
        if not window:
            continue
        sm = SequenceMatcher(None, target, window)
        if sm.real_quick_ratio() < threshold:
            continue
        score = sm.ratio()
        if score >= threshold:
            candidates.append((i, j, score))

    if not candidates:
        return None

    best_score = max(c[2] for c in candidates)
    near = [c for c in candidates if c[2] >= best_score - near_best]
    # 겹치는 창들을 시작점 기준 클러스터로 묶고, 마지막 클러스터의 최고점을 고른다.
    near.sort(key=lambda c: c[0])
    clusters: list[list[tuple[int, int, float]]] = []
    for cand in near:
        if clusters and cand[0] <= clusters[-1][-1][1]:
            clusters[-1].append(cand)
        else:
            clusters.append([cand])
    last = max(clusters[-1], key=lambda c: c[2])
    i, j, score = last

    # 끝 경계 미세조정: j를 ±4단어 움직여 점수가 오르면 채택
    best = (i, j, score)
    for jj in range(max(i, j - 4), min(len(norm_words) - 1, j + 4) + 1):
        window = "".join(norm_words[i:jj + 1])
        if not window:
            continue
        s = SequenceMatcher(None, target, window).ratio()
        if s > best[2]:
            best = (i, jj, s)
    return best
