@echo off
chcp 65001 >nul
REM ============================================================
REM  并行执行 + 失败自动重跑
REM
REM  -n 4          用4个进程并行，速度提升约3倍
REM  --reruns 2    失败的用例自动重跑2次，过滤偶发失败
REM  --reruns-delay 3   重跑前等3秒
REM
REM  注意：被测站点有反爬限流，并行数不宜过高，建议不超过4
REM ============================================================
cd /d "%~dp0.."
echo 正在并行执行测试（4进程 + 失败重跑2次）...
python -m pytest testcases sites -m "not crawl" -n 4 --reruns 2 --reruns-delay 3 -v
echo.
echo 报告: reports\report.html
pause
