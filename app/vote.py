"""다수결 투표 — 정확도의 핵심.

같은 자막을 여러 프레임에서 OCR한 리드들을 글자별 다수결로 합쳐, 랜덤 OCR 오류를 지운다.
안정 구간에서 뽑은 K개 리드가 서로 크게 다르면 일치도가 낮아지고 호출측이 '확인 필요'로 보류한다.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


@dataclass
class OcrRead:
    text: str
    confidence: float = 1.0


@dataclass
class VoteResult:
    text: str            # 합의 텍스트
    agreement: float     # 투표 일치도 0~1 (위치별 다수결 × 길이 일치)
    confidence: float    # 평균 OCR 박스 신뢰도 0~1


_WS = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    """공백 정리·트림 (프레임별 공백 jitter 흡수)."""
    return _WS.sub(" ", (s or "").strip())


def majority_vote(reads: list[OcrRead]) -> VoteResult:
    texts = [normalize_text(r.text) for r in reads]
    nonempty = [(t, r) for t, r in zip(texts, reads) if t]
    if not nonempty:
        return VoteResult(text="", agreement=0.0, confidence=0.0)

    only_texts = [t for t, _ in nonempty]
    mean_conf = sum(r.confidence for _, r in nonempty) / len(nonempty)

    # 최빈 길이를 기준으로 같은 길이 리드끼리 위치별 다수결
    length_counts = Counter(len(t) for t in only_texts)
    modal_len = length_counts.most_common(1)[0][0]
    same_len = [t for t in only_texts if len(t) == modal_len]

    chars: list[str] = []
    pos_scores: list[float] = []
    for pos in range(modal_len):
        col = Counter(t[pos] for t in same_len)
        ch, cnt = col.most_common(1)[0]
        chars.append(ch)
        pos_scores.append(cnt / len(same_len))

    consensus = "".join(chars)
    pos_agreement = (sum(pos_scores) / len(pos_scores)) if pos_scores else 0.0
    len_agreement = len(same_len) / len(only_texts)
    agreement = pos_agreement * len_agreement
    return VoteResult(text=consensus, agreement=agreement, confidence=mean_conf)
