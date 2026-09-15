@echo off
REM RollingPlan - Windows 打包脚本
REM 用法：双击运行，或在 cmd 里执行 build_windows.bat
REM 前提：Windows 上装了 Python（3.10+），且加到 PATH

setlocal enabledelayedexpansion

echo === RollingPlan Windows 打包脚本 ===
echo.

REM 1. 检查 Python
where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)

echo [1/5] Python 检查通过
python --version

REM 2. 进入脚本所在目录
cd /d "%~dp0"
echo [2/5] 当前目录: %CD%

REM 3. 安装依赖
echo.
echo [3/5] 安装依赖（PyQt5 + pyinstaller）...
python -m pip install --upgrade pip
python -m pip install PyQt5 pyinstaller
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

REM 4. 打包
echo.
echo [4/5] 开始打包（这会要 1-2 分钟）...
python -m PyInstaller --onefile --windowed --name RollingPlan ^
    --distpath dist ^
    --workpath build ^
    --specpath . ^
    rollingplan.py
if errorlevel 1 (
    echo [错误] 打包失败
    pause
    exit /b 1
)

REM 5. 完成
echo.
echo === 打包完成 ===
echo exe 位置: %CD%\dist\RollingPlan.exe
echo.
echo 双击 dist\RollingPlan.exe 运行
echo.
pause
