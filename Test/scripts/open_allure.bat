@echo off
chcp 65001 >nul
REM ============================================================
REM  生成并打开 Allure 报告
REM  前置条件：已安装 Java 和 Allure 命令行工具
REM ============================================================
cd /d "%~dp0.."

where allure >nul 2>nul
if errorlevel 1 (
    echo.
    echo [错误] 未检测到 allure 命令
    echo.
    echo 请先完成以下两步：
    echo   1. 安装 Java: https://adoptium.net/
    echo   2. 下载 Allure: https://github.com/allure-framework/allure2/releases
    echo      解压后把 bin 目录加入系统 Path 环境变量
    echo.
    echo 装好后重开终端再运行本脚本。
    echo.
    pause
    exit /b 1
)

if not exist "reports\allure-results" (
    echo [错误] 找不到测试结果，请先执行一次测试
    pause
    exit /b 1
)

echo 正在生成 Allure 报告...
allure serve reports\allure-results
