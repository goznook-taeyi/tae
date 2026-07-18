"""대본-전사 정렬(align) 테스트 — STT 없이 합성 단어 목록으로 검증."""

import pytest

from shortform_editor import align
from shortform_editor.align import ScriptUnit


def _words(*items):
    """items: (start, end, text) 목록 → 단어 dict 목록."""
    return [{"start": s, "end": e, "text": t} for s, e, t in items]


def _speech(text: str, start: float, per_word: float = 0.4):
    """문장을 단어들로 펼쳐 타임스탬프를 붙인다."""
    out = []
    cursor = start
    for w in text.split():
        out.append({"start": cursor, "end": cursor + per_word, "text": w})
        cursor += per_word
    return out


class TestNormalize:
    def test_keeps_hangul_latin_digits(self):
        assert align.normalize("필러가 0.2cc, 됩니다!") == "필러가02cc됩니다"

    def test_strip_directions_removes_labels_and_parens(self):
        s = "PD: 원장님, 그 뉴스 보셨어요? (웃음) / 원장: 봤죠."
        out = align.strip_directions(s)
        assert "PD" not in out and "웃음" not in out and "원장:" not in out
        assert "뉴스" in out and "봤죠" in out


class TestWordsFromCues:
    def test_splits_cue_by_char_share(self):
        cues = [{"start": 0.0, "end": 2.0, "text": "안녕하세요 반갑습니다"}]
        words = align.words_from_cues(cues)
        assert len(words) == 2
        assert words[0]["start"] == 0.0
        assert words[-1]["end"] == 2.0
        assert words[0]["end"] <= words[1]["start"] + 1e-9


class TestAlignScript:
    def test_finds_section_in_order(self):
        words = (_speech("여름이라 시술 미루는 분들 많죠", 0.0)
                 + _speech("솔직하게 말할게요 필러는 햇빛에 녹지 않아요", 10.0)
                 + _speech("댓글에 여름시술 남겨주세요", 30.0))
        units = [
            ScriptUnit("hook", "여름이라 시술 미루는 분들 많죠", "hook#1"),
            ScriptUnit("main", "솔직하게 말할게요 필러는 햇빛에 녹지 않아요", "main#1"),
            ScriptUnit("cta", "댓글에 여름시술 남겨주세요", "cta#1"),
        ]
        result = align.align_script(words, units)
        assert len(result.clips) == 3
        assert [c.unit.role for c in result.clips] == ["hook", "main", "cta"]
        # 시간이 순서대로 증가
        assert result.clips[0].start < result.clips[1].start < result.clips[2].start
        # hook 구간이 실제 발화 시각 근처
        assert result.clips[0].start == pytest.approx(0.0, abs=0.2)

    def test_duplicate_takes_pick_last(self):
        """같은 대사가 두 번(NG→최종) 있으면 마지막 테이크를 고른다."""
        line = "필러가 되고 안되는 걸 본인이 알아야 돼요"
        words = (_speech(line, 0.0)          # 1차 테이크(NG)
                 + _speech("아 잠깐만요", 8.0)
                 + _speech(line, 12.0)        # 최종 테이크
                 + _speech("다음 대사입니다 이어서 갑니다", 25.0))
        units = [
            ScriptUnit("hook", line, "hook#1"),
            ScriptUnit("main", "다음 대사입니다 이어서 갑니다", "main#1"),
        ]
        result = align.align_script(words, units)
        assert len(result.clips) == 2
        # 마지막 테이크(12초대)를 선택했는지
        assert result.clips[0].start >= 11.5
        assert result.clips[1].start >= 24.5

    def test_missing_unit_warns_and_continues(self):
        words = _speech("전혀 다른 내용의 발화입니다", 0.0)
        units = [
            ScriptUnit("hook", "완벽히 무관한 대본 조각이라 못 찾는다", "hook#1"),
            ScriptUnit("main", "전혀 다른 내용의 발화입니다", "main#1"),
        ]
        result = align.align_script(words, units)
        assert len(result.warnings) == 1
        assert len(result.clips) == 1
        assert result.clips[0].unit.role == "main"

    def test_clips_do_not_overlap(self):
        words = (_speech("첫 번째 문장입니다 조금 길게 말합니다", 0.0)
                 + _speech("두 번째 문장입니다 바로 이어집니다", 4.0))
        units = [
            ScriptUnit("hook", "첫 번째 문장입니다 조금 길게 말합니다", "hook#1"),
            ScriptUnit("main", "두 번째 문장입니다 바로 이어집니다", "main#1"),
        ]
        result = align.align_script(words, units)
        assert len(result.clips) == 2
        assert result.clips[0].end <= result.clips[1].start + 1e-9
