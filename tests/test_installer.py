"""설치기(installer) 테스트 — 미러 파일·메타·root_meta_info 등록."""

import json
import os

import pytest

from shortform_editor import installer

NOW_US = 1_783_255_000_000_000  # 고정 마이크로초 타임스탬프


@pytest.fixture()
def projects_root(tmp_path):
    """가짜 CapCut draft 루트 (기존 프로젝트 1개 + root_meta_info.json)."""
    root = tmp_path / "com.lveditor.draft"
    existing = root / "기존프로젝트"
    existing.mkdir(parents=True)
    (existing / "draft_content.json").write_text(
        json.dumps({"name": "기존프로젝트", "duration": 1000}), encoding="utf-8")
    (existing / "draft_settings").write_text("settings", encoding="utf-8")
    (existing / "key_value.json").write_text("{}", encoding="utf-8")
    (existing / "draft_meta_info.json").write_text(json.dumps({
        "draft_id": "OLD-ID", "draft_name": "기존프로젝트",
        "cloud_draft_sync": False, "draft_type": "",
        "draft_materials": [{"type": 0, "value": [{"id": "junk"}]}],
        "tm_draft_create": 1, "tm_draft_modified": 2, "tm_duration": 1000,
    }), encoding="utf-8")
    (root / "root_meta_info.json").write_text(json.dumps({
        "all_draft_store": [{
            "draft_name": "기존프로젝트", "draft_id": "OLD-ID",
            "draft_fold_path": "C:/x/기존프로젝트",
            "draft_json_file": "C:/x/기존프로젝트\\draft_content.json",
            "draft_cover": "C:/x/기존프로젝트\\draft_cover.jpg",
            "tm_draft_create": 1, "tm_draft_modified": 2, "tm_duration": 1000,
        }],
        "draft_ids": 5,
        "root_path": "C:/x",
    }), encoding="utf-8")
    return str(root)


def _draft(name="새프로젝트", duration=42_000_000):
    return {"name": name, "duration": duration, "materials": {"videos": []},
            "tracks": []}


class TestWriteProjectFiles:
    def test_writes_content_and_identical_mirrors(self, projects_root):
        project_dir = os.path.join(projects_root, "새프로젝트")
        installer.write_project_files(_draft(), project_dir,
                                      scaffold_dir=os.path.join(
                                          projects_root, "기존프로젝트"),
                                      now_us=NOW_US)
        content = open(os.path.join(project_dir, "draft_content.json"),
                       encoding="utf-8").read()
        for mirror in installer.MIRROR_FILES:
            assert open(os.path.join(project_dir, mirror),
                        encoding="utf-8").read() == content

    def test_meta_patched_with_us_timestamps(self, projects_root):
        project_dir = os.path.join(projects_root, "새프로젝트")
        meta = installer.write_project_files(
            _draft(), project_dir,
            scaffold_dir=os.path.join(projects_root, "기존프로젝트"),
            now_us=NOW_US)
        assert meta["draft_name"] == "새프로젝트"
        assert meta["draft_id"] != "OLD-ID"
        assert meta["tm_draft_create"] == NOW_US  # 마이크로초 그대로
        assert meta["tm_duration"] == 42_000_000
        # 스캐폴드 실측 필드는 물려받는다
        assert "cloud_draft_sync" in meta
        # 이전 프로젝트의 소재 목록은 비운다
        assert meta["draft_materials"][0]["value"] == []
        # 경로는 포워드 슬래시
        assert "\\" not in meta["draft_fold_path"]

    def test_scaffold_aux_files_copied(self, projects_root):
        project_dir = os.path.join(projects_root, "새프로젝트")
        installer.write_project_files(
            _draft(), project_dir,
            scaffold_dir=os.path.join(projects_root, "기존프로젝트"),
            now_us=NOW_US)
        assert os.path.isfile(os.path.join(project_dir, "draft_settings"))
        assert os.path.isfile(os.path.join(project_dir, "key_value.json"))


class TestRegisterDraft:
    def _install(self, projects_root, register=True, name="새프로젝트"):
        return installer.install_project(
            _draft(name), projects_root,
            scaffold_dir=os.path.join(projects_root, "기존프로젝트"),
            backup_dir=os.path.join(projects_root, "_backups"),
            register=register, running_check=lambda: False, now_us=NOW_US)

    def test_registers_entry_first_and_bumps_ids(self, projects_root):
        self._install(projects_root)
        root_meta = json.load(open(
            os.path.join(projects_root, "root_meta_info.json"),
            encoding="utf-8"))
        store = root_meta["all_draft_store"]
        assert store[0]["draft_name"] == "새프로젝트"
        assert store[0]["tm_draft_create"] == NOW_US
        assert store[0]["draft_json_file"].endswith("\\draft_content.json")
        assert len(store) == 2
        assert root_meta["draft_ids"] == 6

    def test_backup_created_before_patch(self, projects_root):
        self._install(projects_root)
        backups = os.listdir(os.path.join(projects_root, "_backups"))
        assert any(b.startswith("root_meta_info_") for b in backups)

    def test_reinstall_same_name_does_not_duplicate(self, projects_root):
        self._install(projects_root)
        self._install(projects_root)
        root_meta = json.load(open(
            os.path.join(projects_root, "root_meta_info.json"),
            encoding="utf-8"))
        names = [e["draft_name"] for e in root_meta["all_draft_store"]]
        assert names.count("새프로젝트") == 1
        assert root_meta["draft_ids"] == 6  # 갱신은 카운터를 늘리지 않음

    def test_refuses_when_capcut_running(self, projects_root):
        with pytest.raises(installer.CapCutRunningError):
            installer.install_project(
                _draft(), projects_root, register=True,
                running_check=lambda: True)

    def test_no_register_skips_root_meta(self, projects_root):
        self._install(projects_root, register=False)
        root_meta = json.load(open(
            os.path.join(projects_root, "root_meta_info.json"),
            encoding="utf-8"))
        assert len(root_meta["all_draft_store"]) == 1


class TestTemplateDiscovery:
    def test_find_template_projects(self, projects_root):
        found = installer.find_template_projects(projects_root)
        assert len(found) == 1
        assert found[0].endswith("기존프로젝트")

    def test_load_template(self, projects_root):
        d = installer.load_template(os.path.join(projects_root, "기존프로젝트"))
        assert d["name"] == "기존프로젝트"
