@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ============================================================
REM GameAssistant 打包脚本
REM 用法:
REM   build.bat            默认目录模式（GameAssistant.exe + 依赖文件）
REM   build.bat onefile    单文件模式（单个 GameAssistant.exe）
REM ============================================================

set "PROJECT_DIR=%~dp0"
set "BUILD_DIR=%PROJECT_DIR%build"
set "VENV_DIR=%PROJECT_DIR%venv"
set "PYTHON=python"

REM 检测虚拟环境
if exist "%VENV_DIR%\Scripts\python.exe" (
    set "PYTHON=%VENV_DIR%\Scripts\python.exe"
    echo [信息] 使用虚拟环境: %VENV_DIR%
) else (
    echo [警告] 未找到虚拟环境，使用系统 Python
)

REM 检查 PyInstaller
"%PYTHON%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [信息] 正在安装 PyInstaller...
    "%PYTHON%" -m pip install pyinstaller
    if errorlevel 1 (
        echo [错误] PyInstaller 安装失败
        pause
        exit /b 1
    )
)

REM 确定打包模式
set "MODE=dir"
set "SPEC_FILE=%PROJECT_DIR%GameAssistant.spec"
set "OUTPUT_NAME=GameAssistant"

if /i "%~1"=="onefile" (
    set "MODE=onefile"
    set "SPEC_FILE=%PROJECT_DIR%GameAssistant_onefile.spec"
    set "OUTPUT_NAME=GameAssistant_single"
)

echo.
echo ============================================================
echo GameAssistant 打包工具
echo 模式: %MODE%
echo 输出目录: %BUILD_DIR%
echo ============================================================
echo.

REM 创建输出目录
if not exist "%BUILD_DIR%" (
    mkdir "%BUILD_DIR%"
)

REM 清理旧的打包文件
echo [信息] 清理旧的打包文件...
if exist "%BUILD_DIR%\%OUTPUT_NAME%" (
    rmdir /s /q "%BUILD_DIR%\%OUTPUT_NAME%"
)
if exist "%BUILD_DIR%\%OUTPUT_NAME%.exe" (
    del /q "%BUILD_DIR%\%OUTPUT_NAME%.exe"
)

REM 执行打包
echo [信息] 开始打包...
cd /d "%PROJECT_DIR%"

"%PYTHON%" -m PyInstaller ^
    --clean ^
    --noconfirm ^
    --distpath "%BUILD_DIR%" ^
    --workpath "%BUILD_DIR%\_build" ^
    --specpath "%BUILD_DIR%\_spec" ^
    "%SPEC_FILE%"

if errorlevel 1 (
    echo.
    echo [错误] 打包失败！
    pause
    exit /b 1
)

REM 目录模式：重命名输出目录
if "%MODE%"=="dir" (
    if exist "%BUILD_DIR%\GameAssistant" (
        if exist "%BUILD_DIR%\%OUTPUT_NAME%" (
            rmdir /s /q "%BUILD_DIR%\%OUTPUT_NAME%"
        )
        rename "%BUILD_DIR%\GameAssistant" "%OUTPUT_NAME%"
    )
)

REM 单文件模式：移动并重命名
if "%MODE%"=="onefile" (
    if exist "%BUILD_DIR%\GameAssistant.exe" (
        if exist "%BUILD_DIR%\%OUTPUT_NAME%.exe" (
            del /q "%BUILD_DIR%\%OUTPUT_NAME%.exe"
        )
        move /y "%BUILD_DIR%\GameAssistant.exe" "%BUILD_DIR%\%OUTPUT_NAME%.exe" >nul
    )
)

REM 清理临时文件
echo [信息] 清理临时文件...
if exist "%BUILD_DIR%\_build" (
    rmdir /s /q "%BUILD_DIR%\_build"
)
if exist "%BUILD_DIR%\_spec" (
    rmdir /s /q "%BUILD_DIR%\_spec"
)
if exist "%BUILD_DIR%\__pycache__" (
    rmdir /s /q "%BUILD_DIR%\__pycache__"
)

echo.
echo ============================================================
echo [成功] 打包完成！
echo 输出位置: %BUILD_DIR%\%OUTPUT_NAME%
if "%MODE%"=="onefile" (
    echo 文件: %OUTPUT_NAME%.exe
)
echo ============================================================
echo.

REM 打开输出目录
echo [信息] 正在打开输出目录...
explorer "%BUILD_DIR%"

endlocal
pause
