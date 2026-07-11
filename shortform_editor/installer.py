"""CapCut(Windows) 드래프트 설치기 — 이 PC의 실측 규칙 반영.

capcut 워크스페이스(C:\\ai-projects\\capcut)에서 검증된 절차를 그대로 따른다:

1. **캡컷이 완전히 종료된 상태에서만** 새 드래프트를 등록한다.
   (실행 중이면 종료 시 메모리 상태가 `root_meta_info.json`을 덮어써 유실됨)
2. **미러 파일 동기화**: `draft_content.json`과 동일한 내용으로
   `draft_content.json.bak`, `template-2.tmp`를 함께 기록한다.
   미러가 없거나 낡으면 새 드래프트가 열리지 않을 수 있다.
3. **root_meta_info.json 등록**: 기존 엔트리를 복제해 이름/id/경로/시각만 패치하고
   맨 앞에 삽입한다. 수정 전 반드시 백업을 남긴다.
4. 타임스탬프는 캡컷 규격인 **마이크로초**로 기록한다.
5. 부속 파일(draft_settings, key_value.json 등)은 스캐폴드(실제 프로젝트 폴더)에서
   복사해 채운다.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import time
import uuid
from typing import Callable, Optional

# 스캐폴드에서 새 프로젝트로 복사할 부속 파일/폴더 (없는 것은 건너뜀)
SCAFFOLD_FILES = (
    "draft_settings",
    "draft_biz_config.json",
    "draft_agency_config.json",
    "draft_agency_info.json",
    "draft_virtual_store.json",
    "key_value.json",
    "performance_opt_info.json",
    "timeline_layout.json",
    "attachment_pc_common.json",
    "draft_cover.jpg",
)
SCAFFOLD_DIRS = ("common_attachment",)

MIRROR_FILES = ("draft_content.json.bak", "template-2.tmp")


class CapCutRunningError(RuntimeError):
    """캡컷이 실행 중이라 등록할 수 없음."""


def capcut_running() -> bool:
    """CapCut.exe 프로세스가 떠 있는지 확인 (Windows)."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq CapCut.exe", "/NH"],
            capture_output=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return b"CapCut.exe" in (out or b"")


def _now_us() -> int:
    return int(time.time() * 1_000_000)


def _dump_json(data: dict, path: str, compact: bool = False) -> None:
    with open(path, "w", encoding="utf-8") as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, f, ensure_ascii=False)


def write_project_files(
    draft: dict,
    project_dir: str,
    scaffold_dir: Optional[str] = None,
    now_us: Optional[int] = None,
) -> dict:
    """프로젝트 폴더에 draft_content + 미러 + 부속 파일 + meta를 기록한다.

    scaffold_dir: 실제 CapCut 프로젝트 폴더. 부속 파일과 draft_meta_info.json의
    실측 구조를 여기서 가져온다(없으면 최소 형태로 생성).
    반환: 기록된 draft_meta_info dict.
    """
    now_us = now_us or _now_us()
    os.makedirs(project_dir, exist_ok=True)
    name = draft.get("name") or os.path.basename(project_dir)

    # 1) 부속 파일 복사 (스캐폴드)
    if scaffold_dir and os.path.isdir(scaffold_dir):
        for fn in SCAFFOLD_FILES:
            src = os.path.join(scaffold_dir, fn)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(project_dir, fn))
        for dn in SCAFFOLD_DIRS:
            src = os.path.join(scaffold_dir, dn)
            dst = os.path.join(project_dir, dn)
            if os.path.isdir(src) and not os.path.isdir(dst):
                shutil.copytree(src, dst)

    # 2) draft_content.json + 미러 파일 (동일 내용 — 캡컷 미러 규칙)
    content_path = os.path.join(project_dir, "draft_content.json")
    _dump_json(draft, content_path)
    for mirror in MIRROR_FILES:
        shutil.copyfile(content_path, os.path.join(project_dir, mirror))

    # 3) draft_meta_info.json — 스캐폴드의 실측 구조를 물려받아 패치
    meta = None
    if scaffold_dir:
        scaffold_meta = os.path.join(scaffold_dir, "draft_meta_info.json")
        if os.path.isfile(scaffold_meta):
            with open(scaffold_meta, encoding="utf-8") as f:
                meta = json.load(f)
    if meta is None:
        meta = {}
    meta = copy.deepcopy(meta)
    # 캡컷 실측 포맷: 폴더 경로는 포워드 슬래시
    fold = os.path.normpath(project_dir).replace("\\", "/")
    meta.update({
        "draft_id": str(uuid.uuid4()).upper(),
        "draft_name": name,
        "draft_fold_path": fold,
        "draft_root_path": fold.rsplit("/", 1)[0],
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_draft_removed": 0,
        "tm_duration": int(draft.get("duration", 0)),
        "draft_removable_storage_device": "",
        "draft_cover": "draft_cover.jpg",
    })
    if "draft_materials" in meta and isinstance(meta["draft_materials"], list):
        # 이전 프로젝트의 소재 목록은 물려받지 않는다
        meta["draft_materials"] = [
            {"type": item.get("type", 0), "value": []}
            if isinstance(item, dict) else item
            for item in meta["draft_materials"]
        ]
    _dump_json(meta, os.path.join(project_dir, "draft_meta_info.json"))
    return meta


def register_draft(
    projects_root: str,
    project_dir: str,
    meta: dict,
    backup_dir: Optional[str] = None,
    now_us: Optional[int] = None,
) -> str:
    """root_meta_info.json에 새 드래프트를 등록한다. 백업 파일 경로를 반환.

    호출 전 캡컷이 종료돼 있어야 한다 (install_project()가 확인).
    """
    now_us = now_us or _now_us()
    root_meta_path = os.path.join(projects_root, "root_meta_info.json")
    if not os.path.isfile(root_meta_path):
        raise FileNotFoundError(f"root_meta_info.json이 없습니다: {root_meta_path}")

    # 백업
    backup_dir = backup_dir or os.path.join(project_dir, "..", "_backups")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"root_meta_info_{stamp}.json")
    shutil.copy2(root_meta_path, backup_path)

    with open(root_meta_path, encoding="utf-8") as f:
        root_meta = json.load(f)
    store = root_meta.get("all_draft_store")
    if not isinstance(store, list):
        raise ValueError("root_meta_info.json 형식이 예상과 다릅니다 "
                         "(all_draft_store 없음).")

    name = meta.get("draft_name", os.path.basename(project_dir))
    # 이미 등록된 같은 이름이 있으면 갱신, 없으면 기존 엔트리 복제
    existing = next((e for e in store if e.get("draft_name") == name), None)
    if existing is not None:
        entry = existing
        store.remove(existing)
    elif store:
        entry = copy.deepcopy(store[0])
    else:
        entry = {}

    # 캡컷 실측 포맷: 폴더는 포워드 슬래시, 파일은 '\\'로 이어붙는 혼합형
    fold = os.path.normpath(project_dir).replace("\\", "/")
    entry.update({
        "draft_name": name,
        "draft_id": meta.get("draft_id", str(uuid.uuid4()).upper()),
        "draft_fold_path": fold,
        "draft_root_path": fold.rsplit("/", 1)[0],
        "draft_json_file": fold + "\\draft_content.json",
        "draft_cover": fold + "\\draft_cover.jpg",
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_duration": int(meta.get("tm_duration", 0)),
    })
    store.insert(0, entry)
    if isinstance(root_meta.get("draft_ids"), int) and existing is None:
        root_meta["draft_ids"] += 1

    _dump_json(root_meta, root_meta_path, compact=True)
    return backup_path


def install_project(
    draft: dict,
    projects_root: str,
    scaffold_dir: Optional[str] = None,
    backup_dir: Optional[str] = None,
    register: bool = True,
    media_paths: Optional[list[str]] = None,
    copy_media: bool = False,
    running_check: Callable[[], bool] = capcut_running,
    now_us: Optional[int] = None,
) -> str:
    """draft를 CapCut 프로젝트로 기록하고 (옵션) 등록까지 수행한다.

    반환: 프로젝트 폴더 경로.
    register=True인데 캡컷이 실행 중이면 CapCutRunningError를 던진다
    (root_meta_info.json은 캡컷 실행 중 수정 금지 — 종료 시 덮어써 파손됨).
    """
    if register and running_check():
        raise CapCutRunningError(
            "CapCut이 실행 중입니다. 새 프로젝트 등록은 캡컷을 완전히 닫은 뒤에만 "
            "안전합니다 — 캡컷을 종료하고 다시 실행해 주세요.")

    name = draft.get("name") or "shortform_auto"
    project_dir = os.path.join(projects_root, name)

    if copy_media and media_paths:
        materials_dir = os.path.join(project_dir, "materials")
        os.makedirs(materials_dir, exist_ok=True)
        remap: dict[str, str] = {}
        for src in media_paths:
            if src and os.path.exists(src):
                dst = os.path.join(materials_dir, os.path.basename(src))
                shutil.copy2(src, dst)
                remap[src] = dst
        _remap_media_paths(draft, remap)

    meta = write_project_files(draft, project_dir, scaffold_dir, now_us=now_us)
    if register:
        register_draft(projects_root, project_dir, meta,
                       backup_dir=backup_dir, now_us=now_us)
    return project_dir


def _remap_media_paths(draft: dict, remap: dict[str, str]) -> None:
    """복사된 미디어로 material 경로를 바꾼다."""
    if not remap:
        return
    for mat in draft.get("materials", {}).get("videos", []):
        p = mat.get("path")
        if p in remap:
            mat["path"] = remap[p]


def find_template_projects(projects_root: str) -> list[str]:
    """draft 루트에서 template 후보(실제 프로젝트 폴더)를 최신순으로 나열한다."""
    if not os.path.isdir(projects_root):
        return []
    out = []
    for entry in os.listdir(projects_root):
        d = os.path.join(projects_root, entry)
        if os.path.isfile(os.path.join(d, "draft_content.json")):
            out.append(d)
    out.sort(key=lambda d: os.path.getmtime(
        os.path.join(d, "draft_content.json")), reverse=True)
    return out


def load_template(project_dir: str) -> dict:
    """실제 프로젝트 폴더에서 draft_content.json을 읽는다."""
    with open(os.path.join(project_dir, "draft_content.json"),
              encoding="utf-8") as f:
        return json.load(f)
