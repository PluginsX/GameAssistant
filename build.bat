@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ============================================================
REM GameAssistant Build Script
REM ============================================================

set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "BUILD_DIR=%PROJECT_DIR%\build"
set "VENV_DIR=%PROJECT_DIR%\venv"
set "PYTHON=python"

set "ENTRY_POINT=gui\__main__.py"

REM --- Icon & resource paths ---
set "ICO_FILE=gui\resources\icons\ico.ico"
set "ICONS_DIR=gui\resources\icons"

if exist "%VENV_DIR%\Scripts\python.exe" (
    set "PYTHON=%VENV_DIR%\Scripts\python.exe"
    echo [INFO] Using venv: %VENV_DIR%
) else (
    echo [WARN] venv not found, using system Python
)

"%PYTHON%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    "%PYTHON%" -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] PyInstaller install failed
        pause
        exit /b 1
    )
)

set "MODE="

if /I "%~1"=="" goto :ShowMenu
if /I "%~1"=="onefile" set "MODE=onefile"
if /I "%~1"=="dir" set "MODE=dir"
if /I "%~1"=="single" set "MODE=onefile"
if /I "%~1"=="folder" set "MODE=dir"
if /I "%~1"=="directory" set "MODE=dir"

if not defined MODE (
    echo [WARN] Unknown arg: %~1
    echo Usage: build.bat [onefile ^| dir]
    pause
    exit /b 1
)

goto :DoBuild

:ShowMenu
cls
echo.
echo ============================================================
echo            GameAssistant Build Tool
echo ============================================================
echo.
echo Select build mode:
echo.
echo   [1] One-file mode  - single GameAssistant.exe (default)
echo   [2] Directory mode - GameAssistant.exe + files
echo.
echo   Auto-select [1] after 60 seconds
echo.
echo ============================================================
echo.

choice /C 12 /N /T 60 /D 1 /M "Press [1/2]: "
if errorlevel 2 (
    set "MODE=dir"
) else (
    set "MODE=onefile"
)

goto :DoBuild

:DoBuild
if "%MODE%"=="onefile" (
    set "OUT_NAME=GameAssistant_single"
    set "FINAL_EXE=%BUILD_DIR%\GameAssistant_single.exe"
    set "FINAL_DIR=%BUILD_DIR%\GameAssistant_single"
    set "MODE_NAME=One-file"
    set "PYI_MODE=--onefile"
) else (
    set "OUT_NAME=GameAssistant"
    set "FINAL_EXE=%BUILD_DIR%\GameAssistant\GameAssistant.exe"
    set "FINAL_DIR=%BUILD_DIR%\GameAssistant"
    set "MODE_NAME=Directory"
    set "PYI_MODE=--onedir"
)

echo.
echo ============================================================
echo GameAssistant Build Tool
echo Mode: %MODE_NAME%
echo Output: %BUILD_DIR%
echo ============================================================
echo.

if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"

REM ---- ��� exe �Ƿ��������� ----
set "EXE_RUNNING="
tasklist /FI "IMAGENAME eq %OUT_NAME%.exe" 2>nul | find /I "%OUT_NAME%.exe" >nul
if not errorlevel 1 set "EXE_RUNNING=1"

if defined EXE_RUNNING (
    echo.
    echo [WARN] %OUT_NAME%.exe is currently running!
    choice /C YN /N /M "Kill it and continue? [Y/N]: "
    if errorlevel 2 (
        echo [INFO] Build cancelled by user.
        pause
        exit /b 0
    ) else (
        echo [INFO] Stopping %OUT_NAME%.exe...
        taskkill /F /IM "%OUT_NAME%.exe" >nul 2>&1
        if errorlevel 1 (
            echo [ERROR] Failed to kill %OUT_NAME%.exe
            pause
            exit /b 1
        )
        echo [OK] Process terminated.
    )
)

echo [INFO] Cleaning old outputs...
if exist "%BUILD_DIR%\GameAssistant" rmdir /s /q "%BUILD_DIR%\GameAssistant"
if exist "%BUILD_DIR%\GameAssistant_single" rmdir /s /q "%BUILD_DIR%\GameAssistant_single"
if exist "%BUILD_DIR%\GameAssistant.exe" del /q "%BUILD_DIR%\GameAssistant.exe"
if exist "%BUILD_DIR%\GameAssistant_single.exe" del /q "%BUILD_DIR%\GameAssistant_single.exe"
if exist "%BUILD_DIR%\_build" rmdir /s /q "%BUILD_DIR%\_build"

echo [INFO] Building...
cd /d "%PROJECT_DIR%"

"%PYTHON%" -m PyInstaller ^
    --clean --noconfirm ^
    --distpath "%BUILD_DIR%" ^
    --workpath "%BUILD_DIR%\_build" ^
    %PYI_MODE% ^
    --windowed ^
    --name "%OUT_NAME%" ^
    --icon "%ICO_FILE%" ^
    --add-data "%ICONS_DIR%;gui\resources\icons" ^
    --add-data "%ICO_FILE%;." ^
    --hidden-import "gameassistant.bot.core" ^
    --hidden-import "gameassistant.platform.window_win" ^
    --hidden-import "gameassistant.worker.qt_worker" ^
    --hidden-import "PyQt5.QtSvg" ^
    --exclude-module "tkinter" ^
    --exclude-module "matplotlib" ^
    --exclude-module "scipy" ^
    --exclude-module "numpy" ^
    --exclude-module "pandas" ^
    --exclude-module "cv2" ^
    --exclude-module "sphinx" ^
    --exclude-module "setuptools" ^
    --exclude-module "pip" ^
    --exclude-module "PIL.ImageShow" ^
    --exclude-module "PIL.ImageQt" ^
    "%ENTRY_POINT%"
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo [INFO] Verifying output...
if "%MODE%"=="onefile" (
    if not exist "%FINAL_EXE%" (
        echo [ERROR] Output not found: %FINAL_EXE%
        pause
        exit /b 1
    )
    echo [OK] One-file build complete
    echo Output: %FINAL_EXE%
) else (
    if not exist "%FINAL_EXE%" (
        echo [ERROR] Output not found: %FINAL_EXE%
        pause
        exit /b 1
    )
    echo [OK] Directory build complete
    echo Output: %FINAL_DIR%
)

echo [INFO] Cleaning temp files...
if exist "%BUILD_DIR%\_build" rmdir /s /q "%BUILD_DIR%\_build"

echo.
echo ============================================================
echo [OK] Build complete!
if "%MODE%"=="dir" (
    echo Output dir: %FINAL_DIR%
) else (
    echo Output file: %FINAL_EXE%
)
echo ============================================================
echo.

echo [INFO] Opening output folder...
@REM start "" "%BUILD_DIR%"

endlocal