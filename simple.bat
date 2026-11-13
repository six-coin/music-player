@echo off
chcp 65001 >nul
rem 在虚拟环境里运行轻量音乐播放器；命令行程序需要控制台，所以用 python.exe。
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [Music Player] 还没有安装运行环境。
    echo [Music Player] 请先双击 setup.bat，或在命令行执行：uv sync
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "simple.py"
if errorlevel 2 pause
