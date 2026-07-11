"""전사 기반 자동컷 (대본 정렬 폴백).

실전에서는 기획안(대본)과 실제 발화가 다른 경우가 많다 — 기획안은 주제/제목만
잡아두고 원장님이 즉흥으로 말하는 식. 이때 대본-전사 정렬(align)은 실패하므로,
**전사 자체**를 근거로 편집한다:

1. 무음 구간(단어 사이 긴 공백)에서 끊어 발화 블록을 만든다.
2. 반복 테이크(비슷한 문장이 다시 나옴 = NG 후 재촬영)는 **마지막 것만** 남긴다.
3. 후킹/CTA는 기획안 텍스트와 *느슨하게* 비슷한 블록을 찾아 배치한다
   (즉흥이어도 CTA의 "댓글에 'OO'" 같은 키워드는 대체로 살아있다).
4. 나머지는 촬영 순서 그대로 main.

시간 단위는 '초(float)'. 순수 로직(표준 라이브러리만).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .align import MIN_CLIP_DURATION, PAD_POST, PAD_PRE, normalize

# 단어 사이 공백이 이보다 길면 발화 블록을 끊는다(무음 컷)
MAX_WORD_GAP = 0.8
# 반복 테이크 판정 유사도
TAKE_SIMILARITY = 0.72
# 뒤쪽 몇 블록까지 반복 테이크를 찾을지
TAKE_LOOKAHEAD = 4
# 후킹/CTA 힌트 매칭 최소 유사도 (즉흥 발화 대비 느슨하게)
HINT_THRESHOLD = 0.3

# CTA로 볼 수 있는 단서 단어 (힌트 매칭 실패 시 폴백)
CTA_KEYWORDS = ("댓글", "팔로우", "구독", "남겨", "dm", "저장")


@dataclass
class SpeechBlock:
    """무음 경계로 끊은 연속 발화 구간."""

    start: float
    end: float
    text: str
    norm: str = field(default="", repr=False)

    def __post_init__(self):
        if not self.norm:
            self.norm = normalize(self.text)

    @property
    def duration(self) -> float:
        return self.end - self.start


def blocks_from_words(words: list[dict], max_gap: float = MAX_WORD_GAP,
                      min_duration: float = MIN_CLIP_DURATION) -> list[SpeechBlock]:
    """단어 목록 → 발화 블록 목록 (무음 구간에서 분할)."""
    blocks: list[SpeechBlock] = []
    cur: list[dict] = []
    for w in words:
        if not (w.get("text") or "").strip():
            continue
        if cur and float(w["start"]) - float(cur[-1]["end"]) > max_gap:
            blocks.append(_block(cur))
            cur = []
        cur.append(w)
    if cur:
        blocks.append(_block(cur))
    return [b for b in blocks if b.duration >= min_duration and b.norm]


def _block(ws: list[dict]) -> SpeechBlock:
    return SpeechBlock(
        start=float(ws[0]["start"]), end=float(ws[-1]["end"]),
        text=" ".join((w.get("text") or "").strip() for w in ws))


def _similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def dedupe_takes(blocks: list[SpeechBlock],
                 similarity: float = TAKE_SIMILARITY,
                 lookahead: int = TAKE_LOOKAHEAD) -> list[SpeechBlock]:
    """반복 테이크 제거 — 비슷한 블록이 뒤에 다시 나오면 앞의 것(NG)을 버린다."""
    keep = [True] * len(blocks)
    for i, blk in enumerate(blocks):
        for j in range(i + 1, min(i + 1 + lookahead, len(blocks))):
            if _similar(blk.norm, blocks[j].norm) >= similarity:
                keep[i] = False  # 뒤 테이크가 최종본
                break
    return [b for b, k in zip(blocks, keep) if k]


def _best_block(blocks: list[SpeechBlock], hint: str,
                threshold: float, prefer_last: bool = False):
    """힌트 텍스트와 가장 비슷한 블록 인덱스 (threshold 미만이면 None)."""
    hint_norm = normalize(hint)
    if not hint_norm:
        return None
    scored = [(i, _similar(hint_norm, b.norm)) for i, b in enumerate(blocks)]
    scored = [(i, s) for i, s in scored if s >= threshold]
    if not scored:
        return None
    best_score = max(s for _, s in scored)
    near = [(i, s) for i, s in scored if s >= best_score - 0.05]
    return near[-1][0] if prefer_last else near[0][0]


def plan_blocks(
    blocks: list[SpeechBlock],
    hook_hint: str = "",
    cta_hint: str = "",
    hint_threshold: float = HINT_THRESHOLD,
) -> dict[str, list[SpeechBlock]]:
    """블록들을 hook/main/cta 역할로 배치한다.

    - hook: 힌트(후킹멘트/상단질문)와 가장 비슷한 블록. 없으면 첫 블록.
    - cta:  힌트와 비슷한 블록 중 마지막. 없으면 CTA 단서 단어가 있는 마지막 블록.
    - main: 나머지, 촬영 순서 그대로.
    """
    if not blocks:
        return {}
    used: set[int] = set()

    hook_idx = _best_block(blocks, hook_hint, hint_threshold, prefer_last=True)
    if hook_idx is None:
        hook_idx = 0
    used.add(hook_idx)

    cta_idx = _best_block(blocks, cta_hint, hint_threshold, prefer_last=True)
    if cta_idx is None or cta_idx in used:
        cta_idx = None
        for i in range(len(blocks) - 1, -1, -1):
            if i in used:
                continue
            low = blocks[i].text.lower()
            if any(k in low for k in CTA_KEYWORDS):
                cta_idx = i
                break
    if cta_idx is not None:
        used.add(cta_idx)

    main_blocks = [b for i, b in enumerate(blocks) if i not in used]
    out: dict[str, list[SpeechBlock]] = {"hook": [blocks[hook_idx]]}
    if main_blocks:
        out["main"] = main_blocks
    if cta_idx is not None:
        out["cta"] = [blocks[cta_idx]]
    return out


def pad_blocks(blocks: list[SpeechBlock], pad_pre: float = PAD_PRE,
               pad_post: float = PAD_POST) -> list[SpeechBlock]:
    """블록마다 브레스 여유를 붙이되, 이웃 블록(무음 구간) 안에서만 확장한다."""
    prev_end = 0.0
    for k, b in enumerate(blocks):
        start = max(0.0, b.start - pad_pre, prev_end)
        end = b.end + pad_post
        if k + 1 < len(blocks):
            end = min(end, blocks[k + 1].start)
        b.start, b.end = start, end
        prev_end = end
    return blocks
