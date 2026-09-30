@echo off
chcp 65001 >nul
REM 只跑UI用例
cd /d "%~dp0.."
echo 正在执行UI测试...
python -m pytest -m ui -v
echo.
echo 报告: reports\report.html
pause
