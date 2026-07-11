# -*- coding: utf-8 -*-
"""캡컷 저장공간 정리 도구.

사용법 (캡컷을 완전히 닫은 뒤):
  python tools/cleanup.py report                  # 용량 보고만
  python tools/cleanup.py remove-project <이름>   # 깨진 프로젝트 제거(백업 후 등록 해제)
  python tools/cleanup.py clear cache             # CapCut 편집 캐시 (재생성됨, 안전)
  python tools/cleanup.py clear recycle           # CapCut 휴지통(.recycle_bin)
  python tools/cleanup.py clear cloud             # 클라우드 드래프트 캐시(.cloud_cache_*)
                                                  #   ⚠ 클라우드에 있는 드래프트는 다시 받아짐

프로젝트 제거는 폴더를 지우지 않고 C:\\ai-projects\\capcut\\backups\\removed_* 로
옮기고, root_meta_info.json은 백업 후 해당 엔트리만 뺀다.
"""
import json
import os
import shutil
import subprocess
import sys
import time

LOCAL = os.environ["LOCALAPPDATA"]
DRAFTS = os.path.join(LOCAL, "CapCut", "User Data", "Projects", "com.lveditor.draft")
CACHE = os.path.join(LOCAL, "CapCut", "User Data", "Cache")
BACKUPS = r"C:\ai-projects\capcut\backups"


def capcut_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq CapCut.exe", "/NH"],
                         capture_output=True, text=True).stdout
    return "CapCut.exe" in (out or "")


def guard():
    if capcut_running():
        print("[중단] CapCut이 실행 중입니다. 완전히 닫고 다시 실행하세요.")
        sys.exit(1)


def du(path: str) -> int:
    total = 0
    for r, _, fs in os.walk(path):
        for f in fs:
            try:
                total += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return total


def gb(n: int) -> str:
    return f"{n / (1 << 30):.1f}GB"


def report():
    rows = []
    if os.path.isdir(CACHE):
        rows.append(("편집 캐시 (clear cache)", du(CACHE)))
    for d in os.listdir(DRAFTS):
        p = os.path.join(DRAFTS, d)
        if not os.path.isdir(p):
            continue
        if d.startswith(".cloud_cache"):
            rows.append((f"클라우드 캐시 {d} (clear cloud)", du(p)))
        elif d == ".recycle_bin":
            rows.append(("캡컷 휴지통 (clear recycle)", du(p)))
    rows.sort(key=lambda x: -x[1])
    for name, size in rows:
        print(f"{gb(size):>8}  {name}")
    print(f"{gb(sum(s for _, s in rows)):>8}  합계(정리 가능)")


def remove_project(name: str):
    guard()
    src = os.path.join(DRAFTS, name)
    if not os.path.isdir(src):
        print("[중단] 프로젝트 폴더가 없습니다:", src)
        sys.exit(1)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs(BACKUPS, exist_ok=True)
    # 1) root_meta 백업 + 엔트리 제거
    root_meta = os.path.join(DRAFTS, "root_meta_info.json")
    shutil.copy2(root_meta, os.path.join(BACKUPS, f"root_meta_info_{stamp}.json"))
    meta = json.load(open(root_meta, encoding="utf-8"))
    before = len(meta.get("all_draft_store", []))
    meta["all_draft_store"] = [e for e in meta["all_draft_store"]
                               if e.get("draft_name") != name]
    json.dump(meta, open(root_meta, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    # 2) 폴더는 삭제 대신 백업으로 이동
    dest = os.path.join(BACKUPS, f"removed_{name}_{stamp}")
    shutil.move(src, dest)
    print(f"[완료] '{name}' 제거 — 등록 {before}→{len(meta['all_draft_store'])}건, "
          f"폴더는 {dest} 로 이동")


def clear(kind: str):
    guard()
    targets = []
    if kind == "cache":
        targets = [CACHE]
    elif kind == "recycle":
        targets = [os.path.join(DRAFTS, ".recycle_bin")]
    elif kind == "cloud":
        targets = [os.path.join(DRAFTS, d) for d in os.listdir(DRAFTS)
                   if d.startswith(".cloud_cache")]
    else:
        print("[중단] 알 수 없는 대상:", kind)
        sys.exit(1)
    freed = 0
    for t in targets:
        if not os.path.isdir(t):
            continue
        size = du(t)
        shutil.rmtree(t, ignore_errors=True)
        freed += size
        print(f"삭제: {t} ({gb(size)})")
    print(f"[완료] {gb(freed)} 확보")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "report":
        report()
    elif args[0] == "remove-project" and len(args) > 1:
        remove_project(args[1])
    elif args[0] == "clear" and len(args) > 1:
        clear(args[1])
    else:
        print(__doc__)
