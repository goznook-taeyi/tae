"""원클릭 로컬 실행 부트스트래퍼.

더블클릭용 start_windows.bat / start_mac.command 가 이 스크립트를 호출한다.
하는 일:
  1. .venv 가상환경 생성(없으면) 후 그 안에서 재실행
  2. 의존성 설치(최초 1회, 이후 마커로 스킵) — hanspell(git 필요)은 실패해도 계속
  3. 서버 실행 + 브라우저 자동 오픈 (http://localhost:8000)

환경변수:
  TAE_NO_VENV=1  → venv 없이 현재 파이썬 환경에서 실행(개발/테스트용)
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = ROOT / ".venv"
DEPS_MARKER = VENV_DIR / ".deps_installed"
PORT = int(os.environ.get("TAE_PORT", "8000"))


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def ensure_venv() -> None:
    """venv 밖이면 venv를 만들고 그 파이썬으로 재실행."""
    if os.environ.get("TAE_NO_VENV") == "1":
        return
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if in_venv:
        return
    if not VENV_DIR.exists():
        print("가상환경(.venv) 생성 중...")
        venv.create(VENV_DIR, with_pip=True)
    print("가상환경으로 전환...")
    raise SystemExit(subprocess.call([str(venv_python()), str(Path(__file__).resolve())]))


def pip_install(args: list[str]) -> int:
    return subprocess.call([sys.executable, "-m", "pip", "install", "--quiet", *args])


def install_deps() -> None:
    if os.environ.get("TAE_SKIP_INSTALL") == "1":
        return
    if DEPS_MARKER.exists() and os.environ.get("TAE_NO_VENV") != "1":
        return
    req = ROOT / "requirements.txt"
    lines = [
        ln.strip()
        for ln in req.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    core = [ln for ln in lines if "git+" not in ln]
    extra = [ln for ln in lines if "git+" in ln]  # py-hanspell 등 git 필요 패키지

    print("필수 패키지 설치 중... (최초 1회, 수 분 소요 — OCR 엔진이 커서 오래 걸립니다)")
    if pip_install(core) != 0:
        print("일부 패키지 설치 실패 — 하나씩 재시도합니다.")
        for pkg in core:
            if pip_install([pkg]) != 0:
                print(f"  설치 실패(계속 진행): {pkg}")

    for pkg in extra:
        print(f"선택 패키지 설치 시도: {pkg.split('@')[0].strip()} (git 필요 — 실패해도 앱은 동작)")
        if pip_install([pkg]) != 0:
            print("  ↳ 설치 실패: 맞춤법 검사 없이 OCR/자막 추출만 동작합니다. (git 설치 후 재실행하면 활성화)")

    if os.environ.get("TAE_NO_VENV") != "1":
        DEPS_MARKER.write_text("ok", encoding="utf-8")


def open_browser_later() -> None:
    def _open():
        time.sleep(3)
        webbrowser.open(f"http://localhost:{PORT}")

    threading.Thread(target=_open, daemon=True).start()


def main() -> None:
    ensure_venv()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    install_deps()

    print()
    print("=" * 56)
    print(f"  자막 오타 검수 보조 도구  →  http://localhost:{PORT}")
    print("  종료: 이 창을 닫거나 Ctrl+C")
    print("  ※ 첫 분석 시 한국어 OCR 모델을 내려받아 몇 분 걸립니다")
    print("=" * 56)
    print()

    open_browser_later()
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
