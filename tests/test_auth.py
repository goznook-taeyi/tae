"""비밀번호 게이트 테스트 — APP_PASSWORD 환경변수 기반."""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_factory(monkeypatch):
    """APP_PASSWORD를 지정해 앱을 새로 로드한 TestClient 생성."""

    def make(password: str | None):
        if password is None:
            monkeypatch.delenv("APP_PASSWORD", raising=False)
        else:
            monkeypatch.setenv("APP_PASSWORD", password)
        import app.main as m

        importlib.reload(m)
        return TestClient(m.app)

    yield make
    # 환경 원복 후 모듈 원상 복구
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    import app.main as m

    importlib.reload(m)


def test_no_password_means_open(client_factory):
    c = client_factory(None)
    assert c.get("/").status_code == 200
    assert c.get("/healthz").status_code == 200


def test_gate_blocks_api_and_redirects_browser(client_factory):
    c = client_factory("team-secret")
    # API 성 요청은 401
    r = c.get("/jobs/whatever")
    assert r.status_code == 401
    # 브라우저 탐색은 로그인으로 리다이렉트
    r = c.get("/", headers={"accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login"
    # 예외 경로는 열려 있음
    assert c.get("/healthz").status_code == 200
    assert c.get("/login").status_code == 200


def test_login_flow(client_factory):
    c = client_factory("team-secret")
    # 틀린 비밀번호 → 로그인 페이지 재표시(에러)
    r = c.post("/login", data={"password": "wrong"})
    assert "올바르지 않습니다" in r.text
    # 맞는 비밀번호 → 쿠키 설정 + 리다이렉트 → 이후 접근 허용
    r = c.post("/login", data={"password": "team-secret"}, follow_redirects=False)
    assert r.status_code == 302
    assert "tae_auth" in r.cookies
    assert c.get("/").status_code == 200
    assert c.get("/jobs/none-existent").status_code == 404  # 401 아님 = 게이트 통과


def test_wrong_cookie_rejected(client_factory):
    c = client_factory("team-secret")
    c.cookies.set("tae_auth", "forged-value")
    assert c.get("/jobs/whatever").status_code == 401
