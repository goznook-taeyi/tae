"""구글 드라이브/시트 링크 처리 테스트 — 네트워크 없이 가짜 opener로 검증."""

import io

import pytest

from shortform_editor import gdrive

SHEET_URL = "https://docs.google.com/spreadsheets/d/1AbC_dEf-123/edit#gid=77"
FILE_URL = "https://drive.google.com/file/d/1XyZ_987-abc/view?usp=sharing"


class FakeResponse:
    def __init__(self, body: bytes, ctype: str, headers: dict | None = None):
        self._body = io.BytesIO(body)
        self.headers = {"Content-Type": ctype, **(headers or {})}
        self.headers = _HeaderDict(self.headers)

    def read(self, n: int = -1) -> bytes:
        return self._body.read(n)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class _HeaderDict(dict):
    def get(self, k, default=None):  # 대소문자 무시 (urllib headers 흉내)
        for kk, v in self.items():
            if kk.lower() == str(k).lower():
                return v
        return default


def opener_returning(*responses):
    """호출 순서대로 응답을 돌려주는 가짜 urlopen. 요청 URL을 기록한다."""
    calls = []
    seq = list(responses)

    def _open(req, timeout=None):
        calls.append(req.full_url if hasattr(req, "full_url") else str(req))
        return seq.pop(0)

    _open.calls = calls
    return _open


class TestUrlParsing:
    def test_sheet_id_and_gid(self):
        assert gdrive.sheet_id_from_url(SHEET_URL) == "1AbC_dEf-123"
        assert gdrive.sheet_gid_from_url(SHEET_URL) == "77"
        assert gdrive.sheet_id_from_url("https://example.com") is None

    def test_file_id_variants(self):
        assert gdrive.file_id_from_url(FILE_URL) == "1XyZ_987-abc"
        assert gdrive.file_id_from_url(
            "https://drive.google.com/open?id=AAA-bb_1") == "AAA-bb_1"
        assert gdrive.file_id_from_url(
            "https://drive.google.com/uc?export=download&id=Q_1-w") == "Q_1-w"
        assert gdrive.file_id_from_url(SHEET_URL) is None

    def test_is_google_url(self):
        assert gdrive.is_google_url(FILE_URL)
        assert not gdrive.is_google_url(r"C:\videos\a.mp4")


class TestFetchSheetCsv:
    def test_returns_csv_and_uses_export_url(self):
        opener = opener_returning(
            FakeResponse("no,촬영장소\n1,원장실".encode("utf-8"), "text/csv"))
        text = gdrive.fetch_sheet_csv(SHEET_URL, opener=opener)
        assert "원장실" in text
        assert "/export?format=csv" in opener.calls[0]
        assert "gid=77" in opener.calls[0]

    def test_html_means_private(self):
        opener = opener_returning(
            FakeResponse(b"<html>login</html>", "text/html; charset=utf-8"))
        with pytest.raises(gdrive.DriveAccessError, match="비공개"):
            gdrive.fetch_sheet_csv(SHEET_URL, opener=opener)

    def test_non_sheet_url_rejected(self):
        with pytest.raises(gdrive.DriveAccessError):
            gdrive.fetch_sheet_csv(FILE_URL, opener=opener_returning())


class TestDownloadFile:
    def test_direct_download(self, tmp_path):
        opener = opener_returning(FakeResponse(
            b"VIDEO-BYTES", "video/mp4",
            {"Content-Disposition": 'attachment; filename="촬영본.mp4"'}))
        path = gdrive.download_file(FILE_URL, str(tmp_path), opener=opener)
        assert path.endswith("촬영본.mp4")
        assert open(path, "rb").read() == b"VIDEO-BYTES"
        assert "drive.usercontent.google.com/download" in opener.calls[0]

    def test_confirm_form_retry(self, tmp_path):
        warn_html = (
            '<html><form id="download-form" '
            'action="https://drive.usercontent.google.com/download">'
            '<input type="hidden" name="id" value="1XyZ_987-abc">'
            '<input type="hidden" name="confirm" value="t">'
            '<input type="hidden" name="uuid" value="u-1">'
            "</form></html>").encode()
        opener = opener_returning(
            FakeResponse(warn_html, "text/html"),
            FakeResponse(b"BIGFILE", "application/octet-stream",
                         {"Content-Disposition": 'attachment; filename="big.mp4"'}))
        path = gdrive.download_file(FILE_URL, str(tmp_path), opener=opener)
        assert open(path, "rb").read() == b"BIGFILE"
        assert "uuid=u-1" in opener.calls[1]

    def test_private_file_raises(self, tmp_path):
        opener = opener_returning(
            FakeResponse(b"<html>no form here</html>", "text/html"))
        with pytest.raises(gdrive.DriveAccessError, match="비공개"):
            gdrive.download_file(FILE_URL, str(tmp_path), opener=opener)
