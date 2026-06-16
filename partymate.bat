@echo off

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
uv run python -m partymate %*

if %ERRORLEVEL% NEQ 0 (
    pause
)
