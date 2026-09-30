@echo off
chcp 65001 >nul
REM ============================================================
REM  全量执行（不含巡检和视觉，那两类单独跑）
REM ============================================================
cd /d "%~dp0.."
echo.
echo ============================================================
echo   自动化测试 - 全量执行
echo ============================================================
echo.
python -m pytest testcases sites -m "not crawl" -v
echo.
echo   HTML报告:   reports\report.html
echo   Allure原始: reports\allure-results
echo.
pause
