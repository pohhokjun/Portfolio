@echo off
chcp 65001 >nul
REM ============================================================
REM  质量属性全量：可访问性 / 响应式 / 性能预算 / 容错 / 检测能力
REM  显示浏览器 + 录制追踪，跑完可以用 open_trace.bat 逐步回放
REM ============================================================
cd /d "%~dp0.."
echo 正在执行质量属性测试（会弹出浏览器窗口，属于正常现象）...
echo.
python -m pytest testcases/quality -v --site=saucedemo --headed --pw-trace -rxX
echo.
echo 报告:   reports\report.html
echo 追踪:   scripts\open_trace.bat  可在浏览器里逐步回放
pause
