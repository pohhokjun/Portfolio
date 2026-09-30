@echo off
chcp 65001 >nul
REM 接口用例走本地 mock 服务：断网可跑，还能跑故障注入用例
REM 真站点造不出 500/超时/畸形JSON/限流恢复，这些只有 mock 能测
cd /d "%~dp0.."
echo 正在用本地 mock 服务执行接口测试...
python -m pytest -m api -v --mock
echo.
echo 报告: reports\report.html
pause
