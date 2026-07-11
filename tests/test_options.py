"""EditOptions(포맷·무음 강도·목표 길이·전사 태깅) 반영 테스트 — _compute_edit 순수 검증."""

from shortform_editor import pipeline
from shortform_editor.adapters.kitty_solting import ScriptRow
from shortform_editor.pipeline import EditOptions


def _speech(text, start, per=0.4, gap=0.0):
    out = []
    cursor = start
    for w in text.split():
        out.append({"start": cursor, "end": cursor + per, "text": w})
        cursor += per + gap
    return out


def _cues(words):
    return [dict(w, source_id="v1") for w in words]


def compute(words, row=None, opt=None):
    return pipeline._compute_edit(words, _cues(words), row,
                                  "C:/v.mp4", None, opt)


HOOKISH = "여름이라 시술 미루는 분들 많죠 절반만 맞는 얘기예요"
MAIN1 = "사실 온도랑 필러는 큰 상관이 없거든요 진짜로요"
MAIN2 = "진짜 중요한 건 시술 직후 며칠간의 관리예요 정말로"
CTAISH = "궁금하면 댓글에 여름시술 남겨주세요"

ROW = ScriptRow(no="1", top_question="여름 필러 다 녹아요?",
                hook=HOOKISH, main=f"{MAIN1} / {MAIN2}", cta=CTAISH)


def four_part_words():
    return (_speech(HOOKISH, 0.0) + _speech(MAIN1, 10.0)
            + _speech(MAIN2, 20.0) + _speech(CTAISH, 30.0))


class TestFormats:
    def test_short_has_structure_and_title(self):
        segs, _caps, titles, _w = compute(four_part_words(), ROW,
                                          EditOptions(fmt="short"))
        assert segs[0].role == "hook"
        assert segs[-1].role == "cta"
        assert titles and titles[0]["text"] == ROW.top_question

    def test_mid_keeps_order_no_title(self):
        # 훅 힌트와 비슷한 문장이 '뒤에' 있어도 순서를 바꾸지 않는다
        words = (_speech(MAIN1, 0.0) + _speech(MAIN2, 10.0)
                 + _speech(HOOKISH, 20.0))
        segs, _caps, titles, _w = compute(words, None,
                                          EditOptions(fmt="mid"))
        assert all(s.role == "main" for s in segs)
        starts = [s.src_start for s in segs]
        assert starts == sorted(starts)
        assert not titles

    def test_long_ignores_script_no_title(self):
        segs, _caps, titles, _w = compute(four_part_words(), ROW,
                                          EditOptions(fmt="long"))
        assert all(s.role == "main" for s in segs)
        assert not titles


class TestSilenceStrength:
    def _gappy(self):
        # 문장 중간에 0.3초 공백
        w = _speech("앞부분 발화 입니다 계속", 0.0)
        w += _speech("뒷부분 발화 입니다 계속", w[-1]["end"] + 0.3)
        return w

    def test_tight_cuts_03_gap(self):
        segs, *_ = compute(self._gappy(), None,
                           EditOptions(fmt="long", max_silence=0.2))
        assert len(segs) == 2

    def test_relaxed_keeps_03_gap(self):
        segs, *_ = compute(self._gappy(), None,
                           EditOptions(fmt="long", max_silence=0.4))
        assert len(segs) == 1


class TestTagging:
    def test_deleted_range_removed(self):
        words = four_part_words()
        opt = EditOptions(fmt="long", deleted=[(10.0, 14.5)])  # MAIN1 삭제
        segs, caps, *_ = compute(words, None, opt)
        for s in segs:
            assert not (10.0 <= (s.src_start + s.src_end) / 2 < 14.5)
        assert all("온도랑" not in c["text"] for c in caps)

    def test_pinned_hook_overrides(self):
        words = four_part_words()
        opt = EditOptions(fmt="short", pinned_hook=(20.0, 23.9))  # MAIN2를 훅으로
        segs, *_ = compute(words, ROW, opt)
        hook = [s for s in segs if s.role == "hook"]
        assert len(hook) >= 1
        assert hook[0].src_start >= 19.9
        assert hook[0].src_end <= 24.0
        # 훅으로 쓴 구간이 main에 중복 등장하지 않음
        for s in segs:
            if s.role != "hook":
                assert not (s.src_start < 23.9 and s.src_end > 20.0)

    def test_must_keep_survives_dedupe(self):
        line = "같은 대사를 두 번 말합니다 반복 테이크예요"
        words = (_speech(line, 0.0) + _speech(line, 10.0)
                 + _speech("다른 마무리 멘트입니다 계속", 20.0))
        opt = EditOptions(fmt="long", must_keep=[(0.0, 3.6)])  # 첫 테이크 보호
        segs, *_ = compute(words, None, opt)
        assert any(s.src_start < 4.0 for s in segs)  # 첫 테이크 살아있음


class TestTargetLength:
    def test_drops_main_keeps_hook_cta(self):
        words = four_part_words()
        # 전체 ~16초 → 최대 10초로 압축 강제
        opt = EditOptions(fmt="short", target_range=(5, 10))
        segs, _caps, _titles, warns = compute(words, ROW, opt)
        roles = [s.role for s in segs]
        assert "hook" in roles and "cta" in roles
        total = sum(s.duration for s in segs)
        assert total <= 10.5

    def test_must_keep_protected_from_drop(self):
        words = four_part_words()
        opt = EditOptions(fmt="short", target_range=(3, 8),
                          must_keep=[(20.0, 23.9)])  # MAIN2 보호
        segs, *_ = compute(words, ROW, opt)
        assert any(min(s.src_end, 23.9) - max(s.src_start, 20.0) > 0
                   for s in segs)

    def test_warns_when_too_short(self):
        segs, _c, _t, warns = compute(
            four_part_words(), ROW,
            EditOptions(fmt="short", target_range=(60, 90)))
        assert any("짧습니다" in w for w in warns)
