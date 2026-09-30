@echo off
chcp 65001 >nul
REM 用本次截图更新视觉基线（确认改版无误后再执行）
cd /d "%~dp0.."
echo 正在更新视觉基线...
python -m pytest -m visual --update-baseline -v
echo.
python -m tools.cli baseline list
pause
