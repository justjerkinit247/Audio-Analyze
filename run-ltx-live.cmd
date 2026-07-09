@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo ERROR: .venv\Scripts\python.exe was not found.
    echo Create or restore the repository virtual environment first.
    exit /b 1
)

set "PYTHONPATH=%CD%\src"
".venv\Scripts\python.exe" -m audio_analyze.ltx_live_cli %*
exit /b %ERRORLEVEL%
