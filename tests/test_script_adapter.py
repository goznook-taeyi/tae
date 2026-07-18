"""키티조정기 실제 포맷({title, headers, rows}) 어댑터 테스트."""

import pytest

from shortform_editor.adapters import kitty_solting

HEADERS = ["no", "촬영장소", "상단질문", "후킹멘트(도입부)",
           "main 내용(구체화된 원장님 답변)", "CTA"]

SHEET = {
    "title": "르디테_2026-06-29_여름트렌드10",
    "folderId": "abc123",
    "headers": HEADERS,
    "rows": [
        ["1", "원장실",
         "여름엔 필러 하면 안 된다던데, 다 녹는 거 아니에요?",
         "여름이라 시술 미루는 분들 많죠? 근데 그거, 절반만 맞는 얘기예요.",
         "솔직하게 말할게요. 여름이라고 필러가 햇빛에 녹진 않아요. / "
         "PD: 진짜요? / 원장: (웃음) 필러는 몸 안에서 천천히 분해되는 거라 "
         "바깥 온도랑 직접 상관이 없어요. / 진짜 조심할 건 시술 직후 강한 자외선이에요.",
         "댓글에 '여름시술' 남겨주세요."],
        ["2", "로비", "질문2", "후킹2 문장입니다 충분히 길게.",
         "메인2 내용입니다 충분히 길게 씁니다.", "CTA2 문장입니다."],
    ],
}


class TestParseScriptRows:
    def test_is_script_sheet(self):
        assert kitty_solting.is_script_sheet(SHEET)
        assert not kitty_solting.is_script_sheet({"sections": []})

    def test_parses_columns(self):
        rows = kitty_solting.parse_script_rows(SHEET)
        assert len(rows) == 2
        r = rows[0]
        assert r.no == "1"
        assert r.place == "원장실"
        assert "녹는 거" in r.top_question
        assert r.hook.startswith("여름이라")
        assert r.cta.startswith("댓글에")
        assert r.title == SHEET["title"]

    def test_missing_columns_raises(self):
        bad = {"headers": ["a", "b"], "rows": [["1", "2"]]}
        with pytest.raises(ValueError):
            kitty_solting.parse_script_rows(bad)

    def test_csv_roundtrip(self):
        csv_text = (
            "no,촬영장소,상단질문,후킹멘트(도입부),"
            "main 내용(구체화된 원장님 답변),CTA\n"
            '1,원장실,질문입니다,후킹멘트입니다 충분히 길게,'
            '"메인 내용 / 두 번째 비트입니다 길게",마무리 CTA입니다\n')
        rows = kitty_solting.parse_script_csv(csv_text)
        assert len(rows) == 1
        assert rows[0].top_question == "질문입니다"


class TestScriptUnits:
    def test_units_order_and_roles(self):
        rows = kitty_solting.parse_script_rows(SHEET)
        units = kitty_solting.script_units(rows[0])
        roles = [u.role for u in units]
        # hook … main … cta 순서
        assert roles[0] == "hook"
        assert roles[-1] == "cta"
        assert "main" in roles

    def test_speaker_labels_and_directions_stripped(self):
        rows = kitty_solting.parse_script_rows(SHEET)
        units = kitty_solting.script_units(rows[0])
        joined = " ".join(u.text for u in units)
        assert "PD:" not in joined
        assert "원장:" not in joined
        assert "(웃음)" not in joined

    def test_short_beats_merged(self):
        row = kitty_solting.ScriptRow(
            no="1", hook="아주 긴 후킹멘트 문장입니다 충분히 깁니다",
            main="네. / 맞아요. / 그래서 이렇게 길게 설명을 이어갑니다",
            cta="마무리 멘트입니다 길게")
        units = kitty_solting.script_units(row)
        # "네." "맞아요." 같은 짧은 비트는 다음 비트에 합쳐진다
        for u in units:
            assert len(u.text.replace(" ", "")) >= 8

    def test_to_editplan_rejects_script_sheet(self):
        with pytest.raises(ValueError, match="run_scripted"):
            kitty_solting.to_editplan(SHEET)
