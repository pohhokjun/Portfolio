@echo off
chcp 65001 >nul
REM 显示浏览器窗口执行UI用例，用于调试和演示
REM --headed 显示界面   --slow=500 每步慢放500毫秒
cd /d "%~dp0.."
echo 正在以可视模式执行UI测试（会弹出浏览器窗口）...
python -m pytest -m ui -v --headed --slow=500
pause
