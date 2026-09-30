@echo off
chcp 65001 >nul
REM ============================================================
REM  在浏览器里回放测试追踪
REM
REM  追踪文件里存了每一步操作的 DOM 快照、截图、网络请求、
REM  控制台输出。打开之后可以像看录像一样一帧一帧往回倒，
REM  鼠标停在哪一步就显示那一刻的页面长什么样。
REM
REM  排查偶发失败时，这比看日志和截图高效得多。
REM
REM  用法：
REM    open_trace.bat                    列出全部追踪让你挑
REM    open_trace.bat 用例名的一部分      直接打开匹配到的那个
REM ============================================================
cd /d "%~dp0.."

if not exist "reports\traces\*.zip" (
    echo.
    echo [提示] 还没有追踪文件。
    echo 先跑一次带 --pw-trace 的测试，例如：
    echo     scripts\run_quality.bat
    echo 或   python -m pytest testcases/quality --site=saucedemo --pw-trace
    echo.
    pause
    exit /b 1
)

if "%~1"=="" goto :list

for %%f in ("reports\traces\*%~1*.zip") do (
    echo 正在打开: %%f
    python -m playwright show-trace "%%f"
    goto :eof
)
echo 没有匹配 "%~1" 的追踪文件
goto :list

:list
echo.
echo 现有的追踪文件：
echo ------------------------------------------------------------
dir /b reports\traces\*.zip
echo ------------------------------------------------------------
echo.
echo 用法： open_trace.bat 用例名的一部分
echo 例如： open_trace.bat seeded
echo.
pause
