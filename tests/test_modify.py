"""하이브리드 모드(run_modify) 테스트 — 기존 프로젝트 내용만 수정, 등록 없음."""

import json
import os

import pytest

from shortform_editor import installer, pipeline
from test_pipeline_scripted import ROW, fake_transcribe_words
from test_proto_clone import make_template

NOW_META = {"draft_id": "KEEP-ID", "draft_name": "",
            "cloud_draft_sync": False,
            "tm_draft_create": 1, "tm_draft_modified": 2, "tm_duration": 0}


def make_project(root, name, with_text=True):
    """캡컷이 만든 것처럼 보이는 프로젝트 폴더를 만든다."""
    d = make_template()
    d["id"] = f"CONTENT-{name}"
    if not with_text:
        d["tracks"] = [t for t in d["tracks"] if t["type"] != "text"]
        d["materials"]["texts"] = []
    pdir = os.path.join(root, name)
    os.makedirs(pdir)
    with open(os.path.join(pdir, "draft_content.json"), "w",
              encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    meta = dict(NOW_META, draft_name=name)
    with open(os.path.join(pdir, "draft_meta_info.json"), "w",
              encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    return pdir


@pytest.fixture()
def root(tmp_path):
    return str(tmp_path / "com.lveditor.draft")


def run(pdir, row=ROW, **kw):
    logs = []
    out = pipeline.run_modify(
        pdir, row, progress=logs.append,
        transcribe_words_fn=fake_transcribe_words,
        running_check=lambda: False,
        require_media=False, **kw)
    return out, logs


class TestRunModify:
    def test_rewrites_content_keeps_identity(self, root):
        pdir = make_project(root, "어깨필러")
        run(pdir)
        d = json.load(open(os.path.join(pdir, "draft_content.json"),
                           encoding="utf-8"))
        vsegs = [t for t in d["tracks"] if t["type"] == "video"][0]["segments"]
        assert len(vsegs) == 4  # hook + main×2 + cta (컷 적용됨)
        assert d["id"] == "CONTENT-어깨필러"  # 프로젝트 정체성 유지
        assert d["new_version"] == "175.0.0"  # 자기 스키마 유지
        # 영상 경로는 프로젝트가 원래 참조하던 것
        assert d["materials"]["videos"][0]["path"] == "C:/old.mp4"

    def test_mirrors_and_meta_updated(self, root):
        pdir = make_project(root, "어깨필러")
        run(pdir)
        content = open(os.path.join(pdir, "draft_content.json"),
                       encoding="utf-8").read()
        for mirror in installer.MIRROR_FILES:
            assert open(os.path.join(pdir, mirror),
                        encoding="utf-8").read() == content
        meta = json.load(open(os.path.join(pdir, "draft_meta_info.json"),
                              encoding="utf-8"))
        assert meta["draft_id"] == "KEEP-ID"
        assert meta["tm_draft_modified"] > 1_000_000_000_000_000  # 마이크로초
        assert meta["tm_duration"] > 0

    def test_backup_created_before_write(self, root):
        pdir = make_project(root, "어깨필러")
        original = open(os.path.join(pdir, "draft_content.json"),
                        encoding="utf-8").read()
        run(pdir)
        backups_root = os.path.join(root, "_backups")
        bdirs = os.listdir(backups_root)
        assert len(bdirs) == 1
        backed = open(os.path.join(backups_root, bdirs[0],
                                   "draft_content.json"),
                      encoding="utf-8").read()
        assert backed == original

    def test_no_root_meta_needed_or_touched(self, root):
        pdir = make_project(root, "어깨필러")
        run(pdir)  # root_meta_info.json이 아예 없어도 성공해야 함
        assert not os.path.exists(os.path.join(root, "root_meta_info.json"))

    def test_borrows_subtitle_proto_from_donor(self, root):
        donor = make_project(root, "자막있는프로젝트", with_text=True)
        pdir = make_project(root, "막올린프로젝트", with_text=False)
        out, logs = run(pdir)
        assert any("차용" in m for m in logs)
        d = json.load(open(os.path.join(pdir, "draft_content.json"),
                           encoding="utf-8"))
        assert d["materials"]["texts"]  # 자막이 실제로 들어감
        assert os.path.isdir(donor)

    def test_fails_without_donor_for_textless_project(self, root):
        pdir = make_project(root, "막올린프로젝트", with_text=False)
        with pytest.raises(ValueError, match="자막 스타일"):
            run(pdir)

    def test_refuses_when_capcut_running(self, root):
        pdir = make_project(root, "어깨필러")
        with pytest.raises(installer.CapCutRunningError):
            pipeline.run_modify(pdir, ROW,
                                transcribe_words_fn=fake_transcribe_words,
                                running_check=lambda: True,
                                require_media=False)

    def test_silence_trim_active(self, root):
        """0.2초 이상 무음 컷이 수정 모드에도 적용된다."""
        def gappy_transcribe(path, source_id, language=None):
            words = []
            cursor = 0.0
            # 한 문장 안에 0.5초 무음이 섞인 발화
            for i, w in enumerate("여름이라 시술 미루는 분들 많죠 근데 그거 "
                                  "절반만 맞는 얘기예요".split()):
                words.append({"start": cursor, "end": cursor + 0.4, "text": w})
                cursor += 0.4 + (0.5 if i == 4 else 0.0)
            cues = [dict(w, source_id=source_id) for w in words]
            return cues, words

        pdir = make_project(root, "어깨필러")
        pipeline.run_modify(pdir, None,
                            transcribe_words_fn=gappy_transcribe,
                            running_check=lambda: False, require_media=False)
        d = json.load(open(os.path.join(pdir, "draft_content.json"),
                           encoding="utf-8"))
        vsegs = [t for t in d["tracks"] if t["type"] == "video"][0]["segments"]
        assert len(vsegs) == 2  # 문장 중간 0.5초 무음이 잘려 두 컷이 됨
