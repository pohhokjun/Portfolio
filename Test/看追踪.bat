@echo off
chcp 65001 >nul
REM ============================================================
REM  双击本文件即可查看测试追踪，不需要敲任何命令
REM
REM  它做两件事：
REM    1. 用默认浏览器打开官方在线查看器 trace.playwright.dev
REM    2. 打开存放 zip 的文件夹
REM  然后你把 zip 从文件夹拖进浏览器就行。
REM
REM  说明：trace.playwright.dev 是纯前端页面，文件在你自己浏览器里解析，
REM  不会上传。但如果是公司项目的追踪（里面可能有接口响应、cookie、
REM  内网地址），建议改用 scripts\open_trace.bat 走本地打开。
REM ============================================================
cd /d "%~dp0"

if not exist "reports\traces\*.zip" (
    echo.
    echo   还没有追踪文件。
    echo.
    echo   先跑一次带追踪的测试：双击 scripts\run_quality.bat
    echo   跑完 reports\traces\ 下就会有 zip 了。
    echo.
    pause
    exit /b 1
)

echo.
echo   正在打开在线查看器和追踪文件夹...
echo   把右边文件夹里的 zip 拖到左边网页上即可。
echo.

start "" "https://trace.playwright.dev"
start "" "%~dp0reports\traces"

echo   追踪文件夹: %~dp0reports\traces
echo.
echo   （本窗口可以直接关掉）
timeout /t 8 >nul
