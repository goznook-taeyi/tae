"""구글 드라이브/시트 링크 처리 (인증 없이 — 링크 공유 기반).

씨사일 실무 흐름: 기획안은 키티조정기가 만든 **구글시트 링크**로, 촬영본 영상도
대체로 **드라이브 링크**로 온다. 이 모듈은 그 링크를 직접 받아,

- 시트 링크 → CSV export로 내용을 읽고 (`fetch_sheet_csv`)
- 파일 링크 → 로컬로 내려받는다 (`download_file`, 대용량 확인 토큰 처리 포함)

인증을 쓰지 않으므로 대상이 **"링크가 있는 모든 사용자" 공유**여야 한다.
비공개면 로그인 HTML이 돌아오는데, 이를 감지해 친절한 오류를 던진다.

네트워크 함수는 `opener`(urlopen 호환)를 주입받아 테스트에서 대체할 수 있다.
"""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Callable, Optional

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) shortform-editor"}
TIMEOUT = 60
CHUNK = 1 << 20  # 1MiB

SHARE_HELP = (
    "드라이브에서 파일/시트를 '링크가 있는 모든 사용자 - 뷰어'로 공유했는지 "
    "확인하세요. 비공개면 직접 내려받아 로컬 파일로 선택해도 됩니다.")


class DriveAccessError(RuntimeError):
    """링크 접근 실패 (비공개/삭제/형식 오류)."""


# ---------------------------------------------------------------------------
# 링크 파싱
# ---------------------------------------------------------------------------

_SHEET_RE = re.compile(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)")
_FILE_RES = (
    re.compile(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)"),
    re.compile(r"drive\.(?:usercontent\.)?google\.com/(?:uc|open|download)"
               r"[^#]*[?&]id=([a-zA-Z0-9_-]+)"),
)


def is_google_url(text: str) -> bool:
    t = (text or "").strip().lower()
    return t.startswith("http") and ("google.com" in t)


def sheet_id_from_url(url: str) -> Optional[str]:
    m = _SHEET_RE.search(url or "")
    return m.group(1) if m else None


def sheet_gid_from_url(url: str) -> Optional[str]:
    m = re.search(r"[#?&]gid=(\d+)", url or "")
    return m.group(1) if m else None


def file_id_from_url(url: str) -> Optional[str]:
    for rx in _FILE_RES:
        m = rx.search(url or "")
        if m:
            return m.group(1)
    return None


# ---------------------------------------------------------------------------
# 시트 읽기 (CSV export)
# ---------------------------------------------------------------------------

def fetch_sheet_csv(url: str, opener: Callable = urllib.request.urlopen) -> str:
    """구글시트 링크 → CSV 텍스트. 비공개/오류면 DriveAccessError."""
    sid = sheet_id_from_url(url)
    if not sid:
        raise DriveAccessError("구글시트 링크가 아닙니다: " + (url or "")[:80])
    gid = sheet_gid_from_url(url)
    export = (f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv"
              + (f"&gid={gid}" if gid else ""))
    req = urllib.request.Request(export, headers=UA)
    try:
        with opener(req, timeout=TIMEOUT) as res:
            ctype = (res.headers.get("Content-Type") or "").lower()
            data = res.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise DriveAccessError(
                f"시트에 접근할 수 없습니다(HTTP {e.code}). " + SHARE_HELP) from e
        raise DriveAccessError(f"시트를 여는 데 실패했습니다: {e}") from e
    except OSError as e:
        raise DriveAccessError(f"시트를 여는 데 실패했습니다: {e}") from e
    if "text/html" in ctype:
        raise DriveAccessError("시트에 접근할 수 없습니다(비공개로 보임). "
                               + SHARE_HELP)
    return data.decode("utf-8-sig")


# ---------------------------------------------------------------------------
# 파일 다운로드 (대용량 확인 토큰 처리)
# ---------------------------------------------------------------------------

class _FormParser(HTMLParser):
    """대용량 파일 경고 페이지의 download form(action + hidden input)을 읽는다."""

    def __init__(self):
        super().__init__()
        self.action = ""
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "form" and "download" in (d.get("id") or ""):
            self.action = d.get("action") or ""
        elif tag == "input" and d.get("type") == "hidden" and d.get("name"):
            self.fields[d["name"]] = d.get("value") or ""


def _filename_from_headers(headers, default: str) -> str:
    cd = headers.get("Content-Disposition") or ""
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd)
    if m:
        return urllib.parse.unquote(m.group(1)).strip('" ')
    m = re.search(r'filename="?([^";]+)"?', cd)
    if m:
        return m.group(1).strip()
    return default


def download_file(
    url: str,
    dest_dir: str,
    progress: Optional[Callable[[str], None]] = None,
    opener: Callable = urllib.request.urlopen,
) -> str:
    """드라이브 파일 링크를 dest_dir로 내려받고 로컬 경로를 반환한다."""
    fid = file_id_from_url(url)
    if not fid:
        raise DriveAccessError("드라이브 파일 링크가 아닙니다: " + (url or "")[:80])
    os.makedirs(dest_dir, exist_ok=True)

    # usercontent 다운로드 엔드포인트 + confirm=t 가 대부분의 경우를 통과한다
    dl = (f"https://drive.usercontent.google.com/download?id={fid}"
          f"&export=download&confirm=t")
    req = urllib.request.Request(dl, headers=UA)
    try:
        res = opener(req, timeout=TIMEOUT)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise DriveAccessError(
                f"드라이브 파일에 접근할 수 없습니다(HTTP {e.code}). "
                + SHARE_HELP) from e
        raise DriveAccessError(f"드라이브 파일을 여는 데 실패했습니다: {e}") from e
    except OSError as e:
        raise DriveAccessError(f"드라이브 파일을 여는 데 실패했습니다: {e}") from e

    ctype = (res.headers.get("Content-Type") or "").lower()
    if "text/html" in ctype:
        # 경고 페이지 → form의 hidden 파라미터로 재시도
        html = res.read().decode("utf-8", errors="replace")
        res.close()
        parser = _FormParser()
        parser.feed(html)
        if not parser.action:
            raise DriveAccessError("드라이브 파일에 접근할 수 없습니다"
                                   "(비공개로 보임). " + SHARE_HELP)
        q = urllib.parse.urlencode(parser.fields)
        req = urllib.request.Request(f"{parser.action}?{q}", headers=UA)
        try:
            res = opener(req, timeout=TIMEOUT)
        except OSError as e:
            raise DriveAccessError(f"드라이브 파일을 여는 데 실패했습니다: {e}") from e
        ctype = (res.headers.get("Content-Type") or "").lower()
        if "text/html" in ctype:
            res.close()
            raise DriveAccessError("드라이브 파일에 접근할 수 없습니다"
                                   "(비공개로 보임). " + SHARE_HELP)

    name = _filename_from_headers(res.headers, f"{fid}.mp4")
    dest = os.path.join(dest_dir, name)
    total = 0
    with open(dest, "wb") as f:
        while True:
            chunk = res.read(CHUNK)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
            if progress and total % (50 * CHUNK) < CHUNK:
                progress(f"다운로드 중… {total / CHUNK:.0f}MB")
    res.close()
    if progress:
        progress(f"다운로드 완료: {name} ({total / CHUNK:.0f}MB)")
    if total == 0:
        os.remove(dest)
        raise DriveAccessError("빈 파일이 내려받아졌습니다. " + SHARE_HELP)
    return dest


def default_download_dir() -> str:
    """드라이브 영상 다운로드 기본 폴더."""
    return os.path.join(os.path.expanduser("~"), "Videos", "숏폼자동편집")


# ---------------------------------------------------------------------------
# 이동식 매체(SD카드 등) 로컬 스테이징
# ---------------------------------------------------------------------------
# 실측 사고: DJI SD카드(E:)에서 영상을 바로 고르면 처리 도중 장치가 절전/분리되어
# "[Errno 2] No such file" / ffprobe exit 1 로 죽는다. 이동식·네트워크 드라이브의
# 파일은 처리 전에 로컬 폴더로 복사한다.

_NONFIXED_DRIVE_TYPES = {2, 4, 5}  # REMOVABLE, REMOTE, CDROM


def is_removable_path(path: str) -> bool:
    """경로가 이동식/네트워크/광학 드라이브에 있는지 (Windows 전용, 그 외 False)."""
    if os.name != "nt":
        return False
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    if not drive:
        return False
    try:
        import ctypes
        dtype = ctypes.windll.kernel32.GetDriveTypeW(drive + "\\")
    except Exception:
        return False
    return dtype in _NONFIXED_DRIVE_TYPES


def localize_file(path: str, dest_dir: Optional[str] = None,
                  progress: Optional[Callable[[str], None]] = None,
                  force: bool = False) -> str:
    """이동식 매체의 파일을 로컬로 복사하고 그 경로를 반환한다.

    고정 디스크의 파일은 그대로 돌려준다(force=True면 무조건 복사).
    같은 이름·같은 크기의 사본이 이미 있으면 재복사하지 않는다.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"입력 영상을 찾을 수 없습니다: {path}\n"
            "SD카드/외장 드라이브가 분리되지 않았는지 확인하세요.")
    if not force and not is_removable_path(path):
        return path
    dest_dir = dest_dir or default_download_dir()
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(path))
    src_size = os.path.getsize(path)
    if os.path.isfile(dest) and os.path.getsize(dest) == src_size:
        if progress:
            progress(f"로컬 사본 재사용: {dest}")
        return dest
    if progress:
        progress(f"이동식 드라이브 감지 — 로컬로 복사 중… "
                 f"({src_size / (1 << 20):.0f}MB)")
    import shutil
    tmp = dest + ".part"
    shutil.copy2(path, tmp)
    os.replace(tmp, dest)
    if progress:
        progress(f"복사 완료: {dest}")
    return dest


def resolve_media(path_or_url: str, dest_dir: Optional[str] = None,
                  progress: Optional[Callable[[str], None]] = None) -> str:
    """영상 입력(로컬 경로/드라이브 링크)을 처리 가능한 로컬 경로로 바꾼다.

    - 드라이브 링크 → 다운로드
    - 이동식 매체(SD카드 등)의 파일 → 로컬 복사
    - 고정 디스크의 파일 → 그대로
    - 존재하지 않는 경로 → FileNotFoundError(장치 분리 안내)
    """
    if is_google_url(path_or_url):
        if progress:
            progress("드라이브에서 영상 다운로드 중…")
        return download_file(path_or_url, dest_dir or default_download_dir(),
                             progress=progress)
    return localize_file(path_or_url, dest_dir=dest_dir, progress=progress)
