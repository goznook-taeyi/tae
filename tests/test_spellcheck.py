import pytest

from app.models import CheckType
from app.spellcheck import (
    HanspellChecker,
    NoopSpellChecker,
    SpellCheckError,
    diff_to_issues,
)


def test_diff_to_issues_replace():
    issues = diff_to_issues("오늘 날씨가 좋내요", "오늘 날씨가 좋네요", {"좋네요": 1})
    assert len(issues) == 1
    assert issues[0].token == "좋내요"
    assert issues[0].suggestion == "좋네요"
    assert issues[0].check_type == CheckType.SPELLING


def test_diff_to_issues_no_change():
    assert diff_to_issues("정상 문장", "정상 문장", {}) == []


def test_noop_checker():
    assert NoopSpellChecker().check("아무거나") == []


def test_hanspell_retries_then_fails(monkeypatch):
    checker = HanspellChecker(max_retries=2, backoff_s=0)

    class Boom:
        def check(self, text):
            raise RuntimeError("network down")

    checker._spell_checker = Boom()
    monkeypatch.setattr("time.sleep", lambda *_: None)
    with pytest.raises(SpellCheckError):
        checker.check("문장")


def test_hanspell_succeeds_after_retry(monkeypatch):
    checker = HanspellChecker(max_retries=3, backoff_s=0)

    class Flaky:
        def __init__(self):
            self.n = 0

        def check(self, text):
            self.n += 1
            if self.n < 2:
                raise RuntimeError("temporary")

            class R:
                original = "좋내요"
                checked = "좋네요"
                words = {"좋네요": 1}

            return R()

    checker._spell_checker = Flaky()
    monkeypatch.setattr("time.sleep", lambda *_: None)
    issues = checker.check("좋내요")
    assert issues[0].suggestion == "좋네요"


def test_hanspell_empty_text_skips_backend():
    checker = HanspellChecker()
    # 백엔드 미설정이어도 빈 문자열은 호출 없이 통과
    assert checker.check("   ") == []
