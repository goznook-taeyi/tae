"""프로토타입 복제(build_draft + 실측 template) 테스트.

실제 CapCut(8.9.1/draft v175)의 구조를 본뜬 가짜 template으로,
세그먼트/material이 실측 스키마 그대로 복제되는지 검증한다.
"""

import json

from shortform_editor import capcut_draft
from shortform_editor.capcut_draft import sequential_id_gen
from shortform_editor.timeline import Segment


def make_template():
    """실측 draft를 축소한 가짜 template (스키마 특징 유지)."""
    video_seg = {
        "id": "SEG-V1", "material_id": "MAT-V1",
        "source_timerange": {"start": 0, "duration": 5_000_000},
        "target_timerange": {"start": 0, "duration": 5_000_000},
        "extra_material_refs": ["X-SPEED", "X-ANIM", "X-COLOR"],
        "speed": 1.0, "volume": 1.0, "visible": True,
        "group_id": "old-group", "keyframe_refs": ["kf1"],
        "common_keyframes": [{"id": "ck"}],
        "clip": {"alpha": 1.0, "rotation": 0.0,
                 "scale": {"x": 1.3, "y": 1.3},
                 "transform": {"x": 0.1, "y": 0.2},
                 "flip": {"horizontal": False, "vertical": False}},
        "hdr_settings": {"intensity": 1.0, "mode": 1},  # 실측에만 있는 필드
        "enable_adjust": True, "render_index": 0,
    }
    text_seg = {
        "id": "SEG-T1", "material_id": "MAT-T1",
        "target_timerange": {"start": 0, "duration": 2_000_000},
        "extra_material_refs": ["X-TANIM"],
        "visible": True, "render_index": 14001, "group_id": "",
        "clip": {"alpha": 1.0, "rotation": 0.0,
                 "scale": {"x": 1.0, "y": 1.0},
                 "transform": {"x": 0.0, "y": -0.367},
                 "flip": {"horizontal": False, "vertical": False}},
        "caption_info": None,  # 실측에만 있는 필드
    }
    content = json.dumps({
        "text": "원래 자막",
        "styles": [{"range": [0, 5], "size": 11,
                    "font": {"path": "C:/f/GmarketSans.otf", "id": ""},
                    "bold": True}],
    }, ensure_ascii=False)
    return {
        "id": "TEMPLATE-ID",
        "canvas_config": {"width": 1080, "height": 1920, "ratio": "original",
                          "background": None},
        "duration": 5_000_000, "fps": 30.0,
        "keyframes": {"videos": [{"id": "kf1"}], "texts": []},
        "keyframe_graph_list": [{"old": True}],
        "config": {"some_real_flag": True},
        "materials": {
            "videos": [{"id": "MAT-V1", "type": "video", "path": "C:/old.mp4",
                        "material_name": "old.mp4", "duration": 5_000_000,
                        "width": 1080, "height": 1920, "has_audio": True,
                        "crop": {"upper_left_x": 0.1, "upper_left_y": 0.1,
                                 "lower_right_x": 0.9, "lower_right_y": 0.9},
                        "local_material_id": "lib-123",
                        "beauty_body_preset_id": ""}],
            "texts": [{"id": "MAT-T1", "type": "subtitle", "content": content,
                       "words": {"start_time": [1], "end_time": [2],
                                 "text": ["원래"]},
                       "current_words": {"start_time": [], "end_time": [],
                                         "text": []},
                       "recognize_text": "원래 자막", "base_content": "",
                       "font_path": "C:/f/GmarketSans.otf",
                       "background_alpha": 1.0}],
            "speeds": [{"id": "X-SPEED", "type": "speed", "speed": 1.0}],
            "material_animations": [{"id": "X-ANIM", "type": "sticker_animation"},
                                    {"id": "X-TANIM", "type": "sticker_animation"}],
            "material_colors": [{"id": "X-COLOR"}],
            "effects": [{"id": "OLD-EFFECT"}],
        },
        "tracks": [
            {"id": "TR-V", "type": "video", "segments": [video_seg]},
            {"id": "TR-T", "type": "text", "segments": [text_seg]},
        ],
        "version": 360000, "new_version": "175.0.0",
        "platform": {"app_version": "8.9.1"},
    }


def make_segments():
    return [
        Segment("v1", "C:/new.mp4", 10.0, 13.0, 0.0, "hook"),
        Segment("v1", "C:/new.mp4", 30.0, 35.0, 3.0, "main"),
    ]


CAPS = [{"start": 0.5, "end": 2.0, "text": "새 자막입니다"}]
TITLES = [{"start": 0.0, "end": 3.0, "text": "상단 질문 타이틀"}]


class TestHarvest:
    def test_harvest_finds_protos(self):
        protos = capcut_draft.harvest_prototypes(make_template())
        assert protos is not None
        assert protos["video"]["material"]["id"] == "MAT-V1"
        assert protos["subtitle"]["material"]["type"] == "subtitle"

    def test_no_template_returns_none(self):
        assert capcut_draft.harvest_prototypes(None) is None
        assert capcut_draft.harvest_prototypes({"tracks": []}) is None


class TestCloneBuild:
    def build(self):
        return capcut_draft.build_draft(
            make_segments(), CAPS, name="테스트", canvas=(1080, 1920),
            template=make_template(), id_gen=sequential_id_gen(),
            titles=TITLES)

    def test_video_segments_inherit_real_schema(self):
        draft = self.build()
        vtrack = [t for t in draft["tracks"] if t["type"] == "video"][0]
        assert len(vtrack["segments"]) == 2
        seg = vtrack["segments"][0]
        assert "hdr_settings" in seg  # 실측 필드가 복제됨
        assert seg["source_timerange"] == {"start": 10_000_000,
                                           "duration": 3_000_000}
        assert seg["id"] != "SEG-V1"
        # 이전 편집 상태는 초기화
        assert seg["group_id"] == ""
        assert seg["keyframe_refs"] == []
        assert seg["clip"]["scale"] == {"x": 1.0, "y": 1.0}

    def test_video_material_path_replaced_and_shared(self):
        draft = self.build()
        videos = draft["materials"]["videos"]
        assert len(videos) == 1  # 같은 원본은 material 1개 공유
        assert videos[0]["path"] == "C:/new.mp4"
        assert videos[0]["local_material_id"] == ""
        assert "beauty_body_preset_id" in videos[0]  # 실측 필드 유지

    def test_extra_refs_cloned_per_segment(self):
        draft = self.build()
        vtrack = [t for t in draft["tracks"] if t["type"] == "video"][0]
        refs0 = set(vtrack["segments"][0]["extra_material_refs"])
        refs1 = set(vtrack["segments"][1]["extra_material_refs"])
        assert refs0.isdisjoint(refs1)  # 세그먼트마다 부속 material 별도 복제
        assert len(draft["materials"]["speeds"]) == 2
        assert len(draft["materials"]["material_colors"]) == 2

    def test_text_content_patched_styles_kept(self):
        draft = self.build()
        texts = draft["materials"]["texts"]
        sub = [m for m in texts if "새 자막입니다" in m["content"]][0]
        data = json.loads(sub["content"])
        assert data["text"] == "새 자막입니다"
        assert data["styles"][0]["range"] == [0, len("새 자막입니다")]
        assert data["styles"][0]["font"]["path"] == "C:/f/GmarketSans.otf"
        assert sub["words"]["text"] == []  # 이전 단어 타이밍 제거

    def test_title_track_separate(self):
        draft = self.build()
        text_tracks = [t for t in draft["tracks"] if t["type"] == "text"]
        assert len(text_tracks) == 2  # 자막 + 타이틀
        title_texts = [json.loads(m["content"])["text"]
                       for m in draft["materials"]["texts"]]
        assert "상단 질문 타이틀" in title_texts

    def test_old_state_cleared(self):
        draft = self.build()
        assert draft["materials"]["effects"] == []
        assert draft["keyframes"]["videos"] == []
        assert draft["keyframe_graph_list"] == []
        assert draft["id"] != "TEMPLATE-ID"
        assert draft["config"] == {"some_real_flag": True}  # 실측 설정 유지
        assert draft["duration"] == 8_000_000
        assert draft["name"] == "테스트"
