@echo off
title 辅助机器人 - Launcher

cd /d "%~dp0"

REM ---- 管理员权限检查 ----
fltmc >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

REM ---- 定位 Python 解释器 ----
set PYTHON_EXE=
if exist "%~dp0venv\Scripts\pythonw.exe" (
    set PYTHON_EXE=%~dp0venv\Scripts\pythonw.exe
) else if exist "%~dp0venv\Scripts\python.exe" (
    set PYTHON_EXE=%~dp0venv\Scripts\python.exe
) else (
    for %%i in (pythonw.exe) do set PYTHON_EXE=%%~$PATH:i
)

if "%PYTHON_EXE%"=="" (
    echo [错误] 未找到 Python，请先安装依赖：pip install -r requirements.txt
    pause
    exit /b 1
)

REM ---- 启动 GUI ----
start "" "%PYTHON_EXE%" -m gui
