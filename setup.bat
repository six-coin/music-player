@echo off
chcp 65001 >nul
rem 安装或更新运行环境：创建虚拟环境并安装依赖。
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo [Music Player] 没有找到 uv。
    echo [Music Player] 请先安装 uv：https://docs.astral.sh/uv/
    pause
    exit /b 1
)

uv sync
if errorlevel 1 (
    echo [Music Player] 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)

echo [Music Player] 环境已就绪，可以双击 manager.bat。
pause
