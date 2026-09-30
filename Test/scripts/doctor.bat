@echo off
chcp 65001 >nul
REM 环境自检
cd /d "%~dp0.."
python -m tools.cli doctor
echo.
python check_env.py
pause
