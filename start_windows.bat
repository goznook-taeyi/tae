@echo off
chcp 65001 >nul
title 자막 오타 검수 보조 도구
echo.
echo  자막 오타 검수 보조 도구를 시작합니다...
echo.

rem Python 찾기: py 런처 → python 순서
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 scripts\run_local.py
  goto :end
)
python --version >nul 2>nul
if %errorlevel%==0 (
  python scripts\run_local.py
  goto :end
)

echo  [오류] Python이 설치되어 있지 않습니다.
echo  https://www.python.org/downloads/ 에서 설치한 뒤 다시 더블클릭하세요.
echo  (설치 시 "Add python.exe to PATH" 체크 필수!)
echo.

:end
pause
