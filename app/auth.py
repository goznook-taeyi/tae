"""공유 비밀번호 게이트 (팀 공유용 최소 인증).

환경변수 ``APP_PASSWORD``가 설정된 경우에만 활성화된다 — 로컬 개발은 무인증 그대로.
로그인 성공 시 HMAC 서명 쿠키를 발급하고, 미들웨어가 쿠키만 검증한다(세션 저장소 불필요).
"""

from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

COOKIE_NAME = "tae_auth"
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30일

# 인증 없이 접근 가능한 경로
_EXEMPT_PATHS = {"/login", "/healthz"}
_EXEMPT_PREFIXES = ("/static/",)


def get_password() -> str:
    return os.environ.get("APP_PASSWORD", "").strip()


def auth_token(password: str) -> str:
    """비밀번호에서 파생한 쿠키 토큰 (서버 무상태)."""
    return hmac.new(
        password.encode(), b"tae-subtitle-checker-v1", hashlib.sha256
    ).hexdigest()


def is_authenticated(request: Request) -> bool:
    password = get_password()
    if not password:
        return True  # 게이트 비활성
    cookie = request.cookies.get(COOKIE_NAME, "")
    return hmac.compare_digest(cookie, auth_token(password))


class PasswordGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            not get_password()
            or path in _EXEMPT_PATHS
            or path.startswith(_EXEMPT_PREFIXES)
        ):
            return await call_next(request)
        if is_authenticated(request):
            return await call_next(request)
        # 브라우저 탐색은 로그인 페이지로, API 호출은 401 JSON
        accept = request.headers.get("accept", "")
        if request.method == "GET" and "text/html" in accept:
            return RedirectResponse(url="/login", status_code=302)
        return JSONResponse(status_code=401, content={"detail": "인증이 필요합니다."})


def make_login_response(password_input: str) -> RedirectResponse | None:
    """비밀번호가 맞으면 쿠키를 실은 리다이렉트, 틀리면 None."""
    password = get_password()
    if not password or not hmac.compare_digest(password_input, password):
        return None
    resp = RedirectResponse(url="/", status_code=302)
    resp.set_cookie(
        COOKIE_NAME,
        auth_token(password),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return resp
