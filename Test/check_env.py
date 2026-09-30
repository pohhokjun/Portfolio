# -*- coding: utf-8 -*-
"""
环境自检脚本
用法： python check_env.py

作用：一次性检查所有依赖是否就位，避免后面写代码时才发现环境问题。
这个脚本本身也是作品集的一部分——专业项目都会提供 doctor / check 命令。
"""

import os
import sys
import importlib
import subprocess

# ---------------------------------------------------------------
# 检查项定义： (显示名, import名, 是否必须, 说明)
# ---------------------------------------------------------------
PACKAGES = [
    ("pytest",               "pytest",               True,  "测试框架核心"),
    ("pytest-html",          "pytest_html",          True,  "简易HTML报告"),
    ("pytest-xdist",         "xdist",                True,  "并行执行"),
    ("pytest-rerunfailures", "pytest_rerunfailures", True,  "失败重跑"),
    ("playwright",           "playwright",           True,  "UI自动化"),
    ("requests",             "requests",             True,  "接口测试"),
    ("PyYAML",               "yaml",                 True,  "读取测试数据"),
    ("Faker",                "faker",                True,  "随机测试数据"),
    ("Pillow",               "PIL",                  True,  "视觉回归基线比对"),
    ("jsonschema",           "jsonschema",           False, "响应结构校验"),
    ("pytest-cov",           "pytest_cov",           False, "框架自测覆盖率"),
    ("allure-pytest",        "allure_commons",       False, "Allure结果采集"),
    ("python-dotenv",        "dotenv",               False, "敏感配置管理"),
]

TARGET_SITE = "https://automationexercise.com"
API_SITE = "https://automationexercise.com/api/productsList"


def line(char="-", n=62):
    print(char * n)


def check_python():
    print("\n[1/4] Python 版本")
    line()
    v = sys.version_info
    ver = "%d.%d.%d" % (v.major, v.minor, v.micro)
    if v >= (3, 8):
        print("  [OK]   Python %s  （要求 3.8+）" % ver)
        return True
    print("  [FAIL] Python %s 版本过低，需要 3.8 以上" % ver)
    return False


def check_packages():
    print("\n[2/4] Python 依赖包")
    line()
    missing_required = []
    missing_optional = []

    for show_name, import_name, required, desc in PACKAGES:
        try:
            importlib.import_module(import_name)
            print("  [OK]   %-22s %s" % (show_name, desc))
        except ImportError:
            tag = "[FAIL]" if required else "[WARN]"
            print("  %s %-22s %s  ← 未安装" % (tag, show_name, desc))
            (missing_required if required else missing_optional).append(show_name)

    if missing_required:
        print("\n  缺少必需依赖，请执行：")
        print("      pip install -r requirements.txt")
    return not missing_required


def check_browser():
    print("\n[3/4] Playwright 浏览器内核")
    line()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [SKIP] playwright 未安装，跳过")
        return False

    # 本机 Chrome 是 UI 用例的首选（和桌面 Test 快捷方式同一个）；
    # 没装也能跑，框架会退回 Playwright 自带的 Chromium，所以只提示不判失败
    chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    print("  [%s]   本机 Google Chrome%s" % (
        ("OK", "") if os.path.exists(chrome) else ("--", "：没装，UI 用例改用自带 Chromium")))
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        print("  [OK]   Chromium 内核可用")
        return True
    except Exception as exc:
        print("  [FAIL] 浏览器内核不可用")
        print("         %s" % str(exc)[:120])
        print("\n  请执行： python -m playwright install chromium")
        return False


def check_network():
    print("\n[4/4] 被测网站连通性")
    line()
    try:
        import requests
    except ImportError:
        print("  [SKIP] requests 未安装，跳过")
        return False

    ok = True
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    for name, url in [("网站首页", TARGET_SITE), ("接口服务", API_SITE)]:
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": ua})
            if r.status_code == 403 and "bot-protection" in r.text:
                print("  [WARN] %s 返回403：当前IP被站点的机器人防护临时封禁" % name)
                print("         这是环境问题，不是配置错误。")
                print("         解决：等15-60分钟，或换网络（如手机热点）")
                ok = False
                continue
            print("  [OK]   %s  HTTP %s  耗时 %.2fs"
                  % (name, r.status_code, r.elapsed.total_seconds()))
        except Exception as exc:
            print("  [FAIL] %s 无法访问：%s" % (name, type(exc).__name__))
            ok = False
    return ok


def check_optional_tools():
    print("\n[附加] 可选工具（当前阶段不装也没关系）")
    line()
    for name, cmd in [("Java", ["java", "-version"]),
                      ("Allure", ["allure", "--version"]),
                      ("Git", ["git", "--version"])]:
        try:
            subprocess.run(cmd, capture_output=True, timeout=10)
            print("  [OK]   %s 已安装" % name)
        except Exception:
            print("  [--]   %s 未安装（后续阶段再装）" % name)


def main():
    # 输出全是中文，先把控制台切到 UTF-8，
    # 否则英文区系统或输出重定向时会直接 UnicodeEncodeError。
    # 这里不复用 common.logger，因为本脚本的职责就是「依赖还没装好时也能跑」，
    # 一旦 import 项目模块就会连带 import yaml，那就本末倒置了。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    line("=")
    print("  自动化测试项目 - 环境自检")
    line("=")

    results = [
        check_python(),
        check_packages(),
        check_browser(),
        check_network(),
    ]
    check_optional_tools()

    print()
    line("=")
    if all(results):
        print("  全部通过，可以开始写测试用例了。")
    else:
        print("  存在未通过项，请按上面提示处理后重新运行本脚本。")
    line("=")
    print()


if __name__ == "__main__":
    main()
