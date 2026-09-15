@echo off
REM RollingPlan - Windows build script
REM Usage: double-click, or run `build_windows.bat` in cmd
REM Requires: Python 3.10+ on PATH

REM 1. Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] python not found. Install Python 3.10+ and check "Add Python to PATH".
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/5] Python found:
python --version

REM 2. Move to script directory
cd /d "%~dp0"
echo [2/5] Working dir: %CD%

REM 3. Install dependencies
echo.
echo [3/5] Installing dependencies (PyQt5 + pyinstaller + pyqtdarktheme)...
python -m pip install --upgrade pip
python -m pip install PyQt5 pyinstaller pyqtdarktheme
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

REM 4. Clean previous build artifacts
echo.
echo [4/5] Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist RollingPlan.spec del RollingPlan.spec

REM 5. Build
echo.
echo [5/5] Building exe (this takes 1-2 minutes)...
python -m PyInstaller --onefile --windowed --name RollingPlan --distpath dist --workpath build --specpath . --collect-all qdarktheme rollingplan.py
if errorlevel 1 (
    echo [ERROR] pyinstaller failed.
    pause
    exit /b 1
)

echo.
echo === BUILD COMPLETE ===
echo exe: %CD%\dist\RollingPlan.exe
echo.
echo Double-click dist\RollingPlan.exe to run.
echo.
pause
