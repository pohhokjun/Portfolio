@echo off
chcp 65001 >nul
REM ============================================================
REM  视觉回归：截图与基线比对
REM  首次运行建立基线，之后才开始真正比对
REM ============================================================
cd /d "%~dp0.."
python -m pytest -m visual -v
echo.
echo 如果界面是正常改版导致的失败，执行 scripts\update_baseline.bat 更新基线
pause
