@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [VibeResume] Starting resume editor...
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found in PATH. Please install Python or add it to PATH.
  pause
  exit /b 1
)

echo Starting file server on port 4173...
start "VibeResume-File" /B python -m http.server 4173

echo Starting save server on port 4190...
start "VibeResume-Save" /B python -u save-server.py 4190

timeout /t 3 /nobreak >nul
start "" "http://localhost:4173/editor.html"

echo.
echo Editor opened: http://localhost:4173/editor.html
echo Close this window to stop the services.
echo.
pause
