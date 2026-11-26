@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m examples.capacity_demo
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Install Python 3.10 or newer, then run this file again.
    echo https://www.python.org/downloads/windows/
    pause
    exit /b 1
  )
  python -m examples.capacity_demo
)
pause
