@echo off
chcp 65001 >nul
REM 只爬站，不执行用例
cd /d "%~dp0.."
python -m tools.cli explore --gen
echo.
python -m tools.cli sitemap
pause
