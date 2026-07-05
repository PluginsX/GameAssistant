@echo off
title QQ Three Kingdoms Bot - Launcher

cd /d "%~dp0"

REM Check admin privileges
fltmc >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

REM Start GUI with pythonw.exe (no console window)
start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0gui.py"
