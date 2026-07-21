@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 goto usepy
where python >nul 2>nul
if %errorlevel%==0 goto usepython
echo.
echo Python not found.
echo Install it from https://www.python.org/downloads/
echo During install, CHECK "Add python.exe to PATH".
echo Then double-click this file again.
echo.
pause
exit /b

:usepy
py -3 scripts\run_local.py
goto end

:usepython
python scripts\run_local.py
goto end

:end
pause
