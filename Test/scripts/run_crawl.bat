@echo off
chcp 65001 >nul
REM ============================================================
REM  站点巡检：先爬站生成用例，再执行
REM  这是本项目独有的能力，pytest 生态里没有
REM ============================================================
cd /d "%~dp0.."
echo.
echo [1/2] 正在爬站并生成巡检用例...
python -m tools.cli explore --gen
echo.
echo [2/2] 正在执行巡检用例...
python -m pytest -m crawl -v
echo.
pause
