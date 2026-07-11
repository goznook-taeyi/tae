"""대본 정렬 모드(run_scripted) 엔드투엔드 테스트 (STT/FFmpeg/CapCut 없이)."""

import json
import os

import pytest

from shortform_editor import pipeline
from shortform_editor.adapters.kitty_solting import ScriptRow

HOOK = "여름이라 시술 미루는 분들 많죠 근데 그거 절반만 맞는 얘기예요"
MAIN1 = "솔직하게 말할게요 여름이라고 필러가 햇빛에 녹진 않아요"
MAIN2 = "진짜 조심할 건 시술 직후 강한 자외선이에요"
CTA = "댓글에 여름시술 남겨주세요"

ROW = ScriptRow(no="1", place="원장실",
                top_question="여름엔 필러 다 녹는 거 아니에요?",
                hook=HOOK, main=f"{MAIN1} / {MAIN2}", cta=CTA)


def _speech(text, start, per=0.4):
    out = []
    cursor = start
    for w in text.split():
        out.append({"start": cursor, "end": cursor + per, "text": w})
        cursor += per
    return out


def fake_transcribe_words(path, source_id, language=None):
    """촬영본: 인사말 → hook(NG) → hook(최종) → main1 → 잡담 → main2 → cta."""
    words = []
    words += _speech("자 갑니다 하나 둘 셋", 0.0)
    words += _speech(HOOK, 5.0)          # NG 테이크
    words += _speech(HOOK, 20.0)         # 최종 테이크
    words += _speech(MAIN1, 40.0)
    words += _speech("잠깐 물 좀 마실게요", 60.0)
    words += _speech(MAIN2, 70.0)
    words += _speech(CTA, 90.0)
    cues = [{"source_id": source_id, "start": w["start"], "end": w["end"],
             "text": w["text"]} for w in words]
    return cues, words


@pytest.fixture()
def env(tmp_path):
    """가짜 draft 루트 + 실측형 템플릿 프로젝트 + root_meta_info.json."""
    from test_proto_clone import make_template
    root = tmp_path / "com.lveditor.draft"
    tdir = root / "실제프로젝트"
    tdir.mkdir(parents=True)
    (tdir / "draft_content.json").write_text(
        json.dumps(make_template(), ensure_ascii=False), encoding="utf-8")
    (tdir / "draft_settings").write_text("s", encoding="utf-8")
    (tdir / "draft_meta_info.json").write_text(json.dumps(
        {"draft_id": "T-ID", "draft_name": "실제프로젝트",
         "cloud_draft_sync": False,
         "tm_draft_create": 1, "tm_draft_modified": 2}), encoding="utf-8")
    (root / "root_meta_info.json").write_text(json.dumps({
        "all_draft_store": [{"draft_name": "실제프로젝트", "draft_id": "T-ID",
                             "draft_fold_path": "x", "tm_draft_create": 1,
                             "tm_draft_modified": 2, "tm_duration": 0}],
        "draft_ids": 1, "root_path": "x"}), encoding="utf-8")
    return str(root)


def run(env_root, **kw):
    logs = []
    out = pipeline.run_scripted(
        "C:/videos/촬영본.mp4", ROW,
        project_name="르디테_여름1", projects_root=env_root,
        progress=logs.append,
        transcribe_words_fn=fake_transcribe_words,
        probe_duration_fn=lambda p: 100.0,
        probe_resolution_fn=lambda p: (1080, 1920),
        running_check=lambda: False,
        **kw)
    return out, logs


class TestRunScripted:
    def test_creates_registered_project(self, env):
        out, logs = run(env)
        assert os.path.isfile(os.path.join(out, "draft_content.json"))
        # 미러 파일 동기화
        content = open(os.path.join(out, "draft_content.json"),
                       encoding="utf-8").read()
        assert open(os.path.join(out, "draft_content.json.bak"),
                    encoding="utf-8").read() == content
        # root_meta 등록
        root_meta = json.load(open(os.path.join(env, "root_meta_info.json"),
                                   encoding="utf-8"))
        assert root_meta["all_draft_store"][0]["draft_name"] == "르디테_여름1"

    def test_final_take_selected_and_order_kept(self, env):
        out, _ = run(env)
        draft = json.load(open(os.path.join(out, "draft_content.json"),
                               encoding="utf-8"))
        vsegs = [t for t in draft["tracks"] if t["type"] == "video"][0]["segments"]
        assert len(vsegs) == 4  # hook + main×2 + cta
        starts = [s["source_timerange"]["start"] for s in vsegs]
        # hook은 NG(5초대)가 아니라 최종 테이크(20초대)
        assert starts[0] >= 19_000_000
        # 타임라인 순서 = 원본 시간 순서 (hook→main1→main2→cta)
        assert starts == sorted(starts)

    def test_hook_has_title_not_captions(self, env):
        out, _ = run(env)
        draft = json.load(open(os.path.join(out, "draft_content.json"),
                               encoding="utf-8"))
        text_tracks = [t for t in draft["tracks"] if t["type"] == "text"]
        assert len(text_tracks) == 2  # 자막 + 상단질문 타이틀
        all_texts = [json.loads(m["content"])["text"]
                     for m in draft["materials"]["texts"]]
        assert ROW.top_question in all_texts
        # hook 구간(타임라인 초반)에 대사 자막 없음
        hook_dur_us = ([t for t in draft["tracks"] if t["type"] == "video"][0]
                       ["segments"][0]["target_timerange"]["duration"])
        subtitle_track = text_tracks[0]
        for seg in subtitle_track["segments"]:
            mid = (seg["target_timerange"]["start"]
                   + seg["target_timerange"]["duration"] / 2)
            assert mid >= hook_dur_us

    def test_no_register_mode(self, env):
        out, _ = run(env, install=False)
        root_meta = json.load(open(os.path.join(env, "root_meta_info.json"),
                                   encoding="utf-8"))
        names = [e["draft_name"] for e in root_meta["all_draft_store"]]
        assert "르디테_여름1" not in names


def fake_transcribe_improvised(path, source_id, language=None):
    """즉흥 촬영본: 대본과 내용이 다름 (주제만 같음). NG 테이크 1개 포함."""
    words = []
    words += _speech("여름에 시술 받아도 되냐고 정말 많이들 물어보시는데요", 0.0)
    words += _speech("사실 온도나 햇빛이랑 필러는 큰 상관이 없거든요", 15.0)
    words += _speech("사실 온도나 햇빛이랑 필러는 큰 상관이 없어요 진짜로", 30.0)  # 재테이크
    words += _speech("진짜 중요한 건 시술 받고 나서 며칠간의 관리예요", 45.0)
    words += _speech("궁금한 거 있으면 댓글에 여름시술 이라고 남겨주세요", 60.0)
    cues = [{"source_id": source_id, "start": w["start"], "end": w["end"],
             "text": w["text"]} for w in words]
    return cues, words


class TestAutocutFallback:
    def test_falls_back_when_speech_differs_from_script(self, env):
        logs = []
        out = pipeline.run_scripted(
            "C:/videos/즉흥촬영본.mp4", ROW,
            project_name="즉흥테스트", projects_root=env,
            progress=logs.append,
            transcribe_words_fn=fake_transcribe_improvised,
            probe_duration_fn=lambda p: 100.0,
            probe_resolution_fn=lambda p: (1080, 1920),
            running_check=lambda: False)
        assert any("자동컷으로 전환" in m for m in logs)
        draft = json.load(open(os.path.join(out, "draft_content.json"),
                               encoding="utf-8"))
        vsegs = [t for t in draft["tracks"]
                 if t["type"] == "video"][0]["segments"]
        # NG 테이크(15초대)는 빠지고 재테이크(30초대)만 남는다
        starts_s = [s["source_timerange"]["start"] / 1e6 for s in vsegs]
        assert not any(14.0 <= s <= 16.0 for s in starts_s)
        assert any(29.0 <= s <= 31.0 for s in starts_s)
        # hook(주제 비슷한 첫 블록)이 맨 앞, CTA(댓글 유도)가 맨 뒤
        assert starts_s[0] <= 1.0
        assert 59.0 <= starts_s[-1] <= 61.0
        # 상단질문 타이틀은 그대로 얹힘
        all_texts = [json.loads(m["content"])["text"]
                     for m in draft["materials"]["texts"]]
        assert ROW.top_question in all_texts
