"""aeo 모듈 테스트 (순수 로직)."""

import json
import os

from shortform_editor import aeo
from shortform_editor.aeo import Brand


def test_beats_strips_directions_and_speakers():
    b = aeo.beats("PD: 여름엔 이거죠 (웃음) / 원장: 자외선 차단이 핵심입니다")
    assert b == ["여름엔 이거죠", "자외선 차단이 핵심입니다"]


def test_as_question_and_chapter_time():
    assert aeo.as_question("여름 스킨케어 팁") == "여름 스킨케어 팁?"
    assert aeo.as_question("이거 맞아?") == "이거 맞아?"
    assert aeo.format_chapter_time(0) == "0:00"
    assert aeo.format_chapter_time(75) == "1:15"
    assert aeo.format_chapter_time(3725) == "1:02:05"


def _meta():
    return aeo.build_metadata(
        top_question="여름철 기미 관리 어떻게 하나요",
        hook="다들 이거 몰라서 손해봐요",
        main="아침 자외선 차단제 필수 / 비타민C 세럼 병행 / 실내에서도 발라야 합니다",
        cta="원장: 더 궁금하면 댓글 남겨주세요",
        brand=Brand(name="씨사일", one_liner="우리는 영상제작·미디어교육의 씨사일입니다",
                    hashtags=["씨사일"]),
        keywords=["기미관리", "여름스킨케어"],
    )


def test_build_metadata_bluf_and_brand_and_cta():
    m = _meta()
    # 제목은 상단질문 기반
    assert m["title"].startswith("여름철 기미 관리")
    # BLUF = 첫 main 비트
    assert m["bluf"] == "아침 자외선 차단제 필수"
    # 설명은 답변 먼저 → 근거 불릿 → 브랜드 → CTA → 태그
    d = m["description"]
    assert d.startswith("아침 자외선 차단제 필수")
    assert "• 비타민C 세럼 병행" in d
    assert "우리는 영상제작·미디어교육의 씨사일입니다" in d
    assert "더 궁금하면 댓글 남겨주세요" in d
    assert "#기미관리" in d and "#씨사일" in d


def test_faq_is_grounded_question_first():
    m = _meta()
    assert len(m["faq"]) == 1
    q = m["faq"][0]
    assert q["q"].endswith("?")
    assert q["a"].startswith("아침 자외선 차단제 필수")


def test_extra_faq_appended():
    m = aeo.build_metadata(top_question="A는?", main="정답은 B",
                           extra_faq=[{"q": "C는", "a": "D"}])
    assert [f["q"] for f in m["faq"]] == ["A는?", "C는?"]


def test_title_falls_back_to_hook_when_no_question():
    m = aeo.build_metadata(top_question="", hook="첫 후킹 문장", main="본문")
    assert m["title"] == "첫 후킹 문장"


def test_chapters_from_sections_forces_zero_start():
    chs = aeo.chapters_from_sections([
        {"role": "main", "start": 3.0},
        {"role": "hook", "start": 0.0},
        {"role": "cta", "start": 20.0},
    ])
    assert chs[0] == {"label": "후킹", "start": 0.0}
    assert [c["label"] for c in chs] == ["후킹", "핵심", "마무리"]


def test_chapters_render_in_description():
    m = aeo.build_metadata(
        top_question="Q", main="답변",
        chapters=[{"label": "후킹", "start": 0.0}, {"label": "핵심", "start": 3.0}])
    assert "0:00 후킹" in m["description"]
    assert "0:03 핵심" in m["description"]


def test_faq_jsonld_schema():
    ld = aeo.faq_jsonld([{"q": "질문?", "a": "답변"}])
    assert ld["@type"] == "FAQPage"
    assert ld["mainEntity"][0]["acceptedAnswer"]["text"] == "답변"


def test_write_metadata(tmp_path):
    m = _meta()
    paths = aeo.write_metadata(m, str(tmp_path), name="clip1")
    assert os.path.exists(paths["json"])
    assert os.path.exists(paths["publish"])
    assert os.path.exists(paths["faq_md"])
    assert os.path.exists(paths["faq_jsonld"])
    saved = json.load(open(paths["json"], encoding="utf-8"))
    assert saved["title"] == m["title"]
    pub = open(paths["publish"], encoding="utf-8").read()
    assert "[제목]" in pub and "[설명]" in pub
