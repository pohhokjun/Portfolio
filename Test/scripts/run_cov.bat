@echo off
chcp 65001 >nul
REM 框架自测 + 覆盖率
REM 量的是「框架代码被自测覆盖了多少」，不是被测系统的覆盖率。
REM pages/ 和 plugins/ 天然偏低：它们要真浏览器才跑得到，不必强凑数字。
cd /d "%~dp0.."
echo 正在跑框架自测并统计覆盖率...
python -m pytest -m unit -q ^
  --cov=api --cov=common --cov=config --cov=pages --cov=plugins --cov=tools --cov=sites ^
  --cov-report=term-missing:skip-covered ^
  --cov-report=html:reports/coverage
echo.
echo 覆盖率报告: reports\coverage\index.html
pause
