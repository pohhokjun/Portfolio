@echo off
chcp 65001 >nul
REM 只跑P0最高优先级用例：上线前的最后确认
cd /d "%~dp0.."
python -m pytest testcases sites -m p0 -v
pause
