@echo off
chcp 65001 >nul
REM ============================================================
REM  跨浏览器兼容性：同一套用例，三个内核各跑一遍
REM
REM  chromium = Chrome / Edge
REM  firefox  = Firefox
REM  webkit   = Safari（iPhone 上所有浏览器都被强制用这个内核，
REM             所以跑一遍 webkit 约等于在 iPhone 上验过）
REM
REM  首次使用需要先装内核： python -m playwright install firefox webkit
REM ============================================================
cd /d "%~dp0.."

for %%e in (chromium firefox webkit) do (
    echo.
    echo ============================================================
    echo   内核: %%e
    echo ============================================================
    python -m pytest testcases/quality -q --site=saucedemo --browser-engine=%%e -rxX
)
echo.
echo 三个内核都跑完了。报告: reports\report.html
pause
