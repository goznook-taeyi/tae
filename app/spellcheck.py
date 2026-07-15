"""맞춤법 검사 — 교체 가능한 백엔드.

기본 백엔드는 py-hanspell(네이버 맞춤법 검사기 래퍼). 알려진 대로 불안정하므로:
  - 호출마다 지수 백오프 재시도
  - 실패 시 ``SpellCheckError`` — 파이프라인이 세그먼트 단위로 잡아 전체 실행은 계속
  - ``SpellChecker`` 인터페이스 뒤에 두어 나중에 다른 백엔드로 교체 가능

hanspell 오류 코드 → 유형 분류:
  0 정상 / 1 오타(맞춤법) / 2 띄어쓰기 / 3 표준어의심(표현) / 4 통계교정
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from difflib import SequenceMatcher

from .models import CheckType, SpellIssue


class SpellCheckError(Exception):
    """맞춤법 백엔드 호출이 최종적으로 실패했음을 알린다."""


_CODE_TO_TYPE = {
    1: CheckType.SPELLING,
    2: CheckType.SPACING,
    3: CheckType.STYLE,
    4: CheckType.STATISTICAL,
}


def diff_to_issues(
    original: str, checked: str, word_codes: dict[str, int] | None = None
) -> list[SpellIssue]:
    """원문과 교정문을 토큰 단위로 비교해 SpellIssue 목록을 만든다."""
    word_codes = word_codes or {}
    o_tokens = original.split()
    c_tokens = checked.split()
    issues: list[SpellIssue] = []
    sm = SequenceMatcher(None, o_tokens, c_tokens)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        token = " ".join(o_tokens[i1:i2]).strip()
        suggestion = " ".join(c_tokens[j1:j2]).strip()
        if not token and not suggestion:
            continue
        # 교정된 단어의 코드로 유형 추정 (없으면 띄어쓰기/기타 추정)
        ctype = CheckType.UNKNOWN
        for w in c_tokens[j1:j2]:
            if w in word_codes and word_codes[w] in _CODE_TO_TYPE:
                ctype = _CODE_TO_TYPE[word_codes[w]]
                break
        if ctype == CheckType.UNKNOWN and tag != "replace":
            ctype = CheckType.SPACING
        issues.append(
            SpellIssue(token=token, suggestion=suggestion, check_type=ctype)
        )
    return issues


class SpellChecker(ABC):
    @abstractmethod
    def check(self, text: str) -> list[SpellIssue]:
        """이슈 목록 반환. 백엔드 실패 시 SpellCheckError를 raise 해야 한다."""
        raise NotImplementedError


class NoopSpellChecker(SpellChecker):
    """항상 이슈 없음 — 테스트 더블 및 완전 실패 시 graceful fallback."""

    def check(self, text: str) -> list[SpellIssue]:
        return []


class HanspellChecker(SpellChecker):
    def __init__(self, max_retries: int = 3, backoff_s: float = 1.5) -> None:
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self._spell_checker = None  # 지연 로드

    def _get_backend(self):
        if self._spell_checker is None:
            try:
                from hanspell import spell_checker  # type: ignore
            except Exception as exc:  # pragma: no cover - import 환경 의존
                raise SpellCheckError(
                    "hanspell을 불러올 수 없습니다. `pip install -r requirements.txt` 확인. "
                    "네이버 엔드포인트 변경 시 passport 토큰 패치가 필요할 수 있습니다(README 참고)."
                ) from exc
            self._spell_checker = spell_checker
        return self._spell_checker

    def check(self, text: str) -> list[SpellIssue]:
        text = (text or "").strip()
        if not text:
            return []
        backend = self._get_backend()
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = backend.check(text)
                original = getattr(result, "original", text)
                checked = getattr(result, "checked", text)
                words = getattr(result, "words", {}) or {}
                # words 값이 enum/객체일 수 있어 int로 정규화
                word_codes = {
                    k: int(v) for k, v in words.items() if _is_int_like(v)
                }
                return diff_to_issues(original, checked, word_codes)
            except SpellCheckError:
                raise
            except Exception as exc:  # 네트워크/파싱 등
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(self.backoff_s * (2**attempt))
        raise SpellCheckError(
            f"hanspell 검사 실패({self.max_retries}회 재시도): {last_exc}"
        )


def _is_int_like(v) -> bool:
    try:
        int(v)
        return True
    except (TypeError, ValueError):
        return False


def build_checker(engine: str = "hanspell", **kwargs) -> SpellChecker:
    if engine == "noop":
        return NoopSpellChecker()
    return HanspellChecker(**kwargs)
