"""전사 기반 자동컷(autocut) 테스트 — 기획안과 발화가 다른 즉흥 촬영 시나리오."""

from shortform_editor import autocut


def _speech(text, start, per=0.4):
    out = []
    cursor = start
    for w in text.split():
        out.append({"start": cursor, "end": cursor + per, "text": w})
        cursor += per
    return out


class TestBlocks:
    def test_split_on_silence(self):
        words = _speech("첫 번째 문장입니다", 0.0) + _speech("두 번째 문장입니다", 10.0)
        blocks = autocut.blocks_from_words(words)
        assert len(blocks) == 2
        assert blocks[0].text.startswith("첫")
        assert blocks[1].start == 10.0

    def test_no_split_within_gap(self):
        words = _speech("이어지는 한 문장 입니다", 0.0)
        blocks = autocut.blocks_from_words(words)
        assert len(blocks) == 1

    def test_short_blocks_dropped(self):
        words = [{"start": 0.0, "end": 0.3, "text": "음"}] + _speech(
            "정상 길이의 문장입니다", 5.0)
        blocks = autocut.blocks_from_words(words)
        assert len(blocks) == 1
        assert "정상" in blocks[0].text


class TestDedupeTakes:
    def test_keeps_last_take(self):
        line = "필러가 되고 안되는 걸 본인이 알아야 돼요"
        words = (_speech(line, 0.0) + _speech(line + " 그렇죠", 10.0)
                 + _speech("완전히 다른 이야기입니다 계속 갑니다", 20.0))
        blocks = autocut.dedupe_takes(autocut.blocks_from_words(words))
        assert len(blocks) == 2
        assert blocks[0].start >= 10.0  # 첫 테이크(NG)가 빠짐

    def test_different_blocks_kept(self):
        words = (_speech("첫 번째 주제 이야기입니다", 0.0)
                 + _speech("전혀 다른 두 번째 주제입니다", 10.0))
        blocks = autocut.dedupe_takes(autocut.blocks_from_words(words))
        assert len(blocks) == 2


class TestPlanBlocks:
    def _blocks(self):
        words = (_speech("여름에 필러 받아도 되냐고 많이들 물어보세요", 0.0)
                 + _speech("사실 온도랑 필러는 큰 상관이 없거든요", 10.0)
                 + _speech("진짜 중요한 건 시술 직후 관리예요", 20.0)
                 + _speech("궁금하시면 댓글에 여름시술 남겨주세요", 30.0))
        return autocut.blocks_from_words(words)

    def test_roles_assigned_with_hints(self):
        roles = autocut.plan_blocks(
            self._blocks(),
            hook_hint="여름이라 필러 받아도 되는지 물어보는 분들 많죠",
            cta_hint="댓글에 '여름시술' 남겨주세요")
        assert [b.text for b in roles["hook"]][0].startswith("여름에")
        assert "댓글" in roles["cta"][0].text
        assert len(roles["main"]) == 2

    def test_cta_keyword_fallback_without_hint(self):
        roles = autocut.plan_blocks(self._blocks(), hook_hint="", cta_hint="")
        assert "cta" in roles
        assert "댓글" in roles["cta"][0].text

    def test_hook_falls_back_to_first_block(self):
        roles = autocut.plan_blocks(self._blocks(),
                                    hook_hint="완전히 무관한 힌트 텍스트",
                                    cta_hint="")
        assert roles["hook"][0].start == 0.0


class TestTrimSilence:
    def test_cuts_gaps_over_threshold(self):
        """0.2초 이상 무음은 컷 구간 안에서 전부 잘린다."""
        words = (_speech("앞부분 발화입니다 조금 길게", 0.0)
                 + _speech("뒷부분 발화입니다 역시 길게", 5.0))  # 3초 무음
        spans = autocut.trim_silence(words, 0.0, 10.0)
        assert len(spans) == 2
        gap = spans[1][0] - spans[0][1]
        assert gap >= 2.0  # 무음이 실제로 제거됨(두 조각 사이가 벌어짐)

    def test_keeps_short_gaps(self):
        words = [{"start": 0.0, "end": 0.5, "text": "네"},
                 {"start": 0.65, "end": 1.4, "text": "맞아요"},  # 0.15s gap
                 {"start": 1.5, "end": 2.4, "text": "그렇습니다"}]  # 0.1s gap
        spans = autocut.trim_silence(words, 0.0, 3.0)
        assert len(spans) == 1  # 0.2초 미만 공백은 유지

    def test_tiny_fragments_merge_not_drop(self):
        """짧은 발화 조각은 버리지 않고 이웃과 합친다."""
        words = ([{"start": 0.0, "end": 0.2, "text": "네"}]      # 0.2초 조각
                 + _speech("이어지는 본문 발화입니다", 1.0))
        spans = autocut.trim_silence(words, 0.0, 5.0)
        assert spans[0][0] <= 0.0 + 0.01  # "네"가 살아있음
        assert len(spans) == 1

    def test_no_words_returns_original(self):
        assert autocut.trim_silence([], 1.0, 2.0) == [(1.0, 2.0)]

    def test_spans_do_not_overlap_and_stay_inside(self):
        words = (_speech("하나 둘 셋 넷 다섯", 0.0)
                 + _speech("여섯 일곱 여덟 아홉 열", 4.0))
        spans = autocut.trim_silence(words, 0.5, 5.5)
        for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
            assert e1 <= s2
        assert spans[0][0] >= 0.5
        assert spans[-1][1] <= 5.5


class TestPadBlocks:
    def test_padding_stays_within_silence(self):
        words = (_speech("첫 문장입니다 길게 말합니다", 0.0)
                 + _speech("두 번째 문장입니다 역시 길게", 5.0))
        blocks = autocut.blocks_from_words(words)
        autocut.pad_blocks(blocks)
        assert blocks[0].start == 0.0
        assert blocks[0].end <= blocks[1].start  # 이웃 블록과 안 겹침
        assert blocks[0].end > 1.6  # 원래 발화 끝(1.6s)보다 뒤 — post-pad가 붙음
