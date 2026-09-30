@echo off
chcp 65001 >nul
REM 只跑接口用例：不启动浏览器，速度最快
cd /d "%~dp0.."
echo 正在执行接口测试...
python -m pytest -m api -v
echo.
echo 报告: reports\report.html
pause
