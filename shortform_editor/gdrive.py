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
