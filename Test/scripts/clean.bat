@echo off
chcp 65001 >nul
REM 清理历史报告、截图、日志（保留视觉基线）
cd /d "%~dp0.."
echo 正在清理...
if exist "reports\allure-results" rd /s /q "reports\allure-results"
if exist "reports\allure-report" rd /s /q "reports\allure-report"
if exist "reports\screenshots" rd /s /q "reports\screenshots"
if exist "reports\logs" rd /s /q "reports\logs"
if exist "reports\report.html" del /q "reports\report.html"
if exist ".pytest_cache" rd /s /q ".pytest_cache"
echo 清理完成（视觉基线已保留）
echo 如需清空基线：python -m tools.cli baseline clear
pause
