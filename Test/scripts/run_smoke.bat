@echo off
chcp 65001 >nul
REM 只跑冒烟用例：提测后的快速验证，1-2分钟出结果
cd /d "%~dp0.."
echo 正在执行冒烟测试...
python -m pytest testcases sites -m "smoke" -v
echo.
echo 报告: reports\report.html
pause
