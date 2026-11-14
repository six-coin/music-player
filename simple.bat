@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Failed: Run setup.bat first to install dependencies.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "simple.py"
if errorlevel 2 pause
