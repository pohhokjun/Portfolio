# -*- coding: utf-8 -*-
"""
根级 conftest.py —— 整个框架的心脏

conftest.py 是什么（面试必问）：
    pytest 会自动加载它，不需要 import。
    放在哪个目录，里面的 fixture 就对哪个目录及其子目录生效。
    这就是「层级化的依赖注入」。

    本项目的三层结构：
        conftest.py                 全局：命令行参数、浏览器、日志、报告钩子
        sites/<站>/conftest.py      站点专用：本站配置、接口客户端、页面对象
        sites/<站>/tests/ui/conftest.py  更内层：只有 UI 用例需要的登录态

fixture 的作用域（面试必问）：
    function  每个用例执行一次      默认值，最安全但最慢
    class     每个测试类执行一次
    module    每个 .py 文件执行一次
    session   整个测试会话执行一次  最快，但要注意状态污染

    本项目：浏览器 session 级（启动慢，复用），页面 function 级（保证隔离）
"""

import os
import shutil
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import allure
import pytest
from playwright.sync_api import sync_playwright

from config.settings import SCREENSHOT_DIR, REPORT_DIR, TRACE_DIR
from common.logger import get_logger

log = get_logger("conftest")


# ===============================================================
# 注册自定义插件
#
# ★ 这是「自研能力接入 pytest 生态」的接线口 ★
#   plugins/ 下的每个模块都是从原自研平台迁移改造来的能力，
#   通过 pytest_plugins 声明后，它们的 fixture 和 hook
#   就和 pytest 原生功能一样可用了。
# ===============================================================
pytest_plugins = [
    "plugins.site_plugin",        # 被测系统：--site 选站、各站 cfg、--mock 起假服务
    "plugins.visual_plugin",      # UI 截图基线比对（视觉回归）
    "plugins.cleanup_plugin",     # 测试数据台账与自动清理
    "plugins.account_plugin",     # 账号池租借（并行防抢号）
    "plugins.notify_plugin",      # 结果通知（Telegram / Webhook）
    "plugins.summary_plugin",     # 跑完自动生成测试总结报告（结论，非明细）
]


# ===============================================================
# 一、自定义命令行参数
#     用法： pytest --site=saucedemo --env=prod --headed
# ===============================================================
def pytest_addoption(parser):
    parser.addoption("--site", action="store", default=None,
                     help="被测系统（sites/ 下的文件夹名），默认读 config/defaults.yaml 的 default_site")
    parser.addoption("--env", action="store", default=None,
                     help="运行环境: test / prod（站点的 site.yaml 里配了才有）")
    parser.addoption("--headed", action="store_true", default=False,
                     help="显示浏览器界面（现在已是默认，保留兼容）")
    parser.addoption("--headless", action="store_true", default=False,
                     help="强制无头。跑得快，CI 上必须用")
    parser.addoption("--slow", action="store", default=None, type=int,
                     help="每步操作延迟毫秒数，调试用，如 --slow=500")
    parser.addoption("--browser-engine", action="store", default="chromium",
                     choices=["chromium", "firefox", "webkit"],
                     help="浏览器内核。跨浏览器兼容性测试用，如 --browser-engine=firefox")
    # 不能叫 --trace：pytest 自己已经占用了这个名字（进 pdb 逐行调试），
    # 重名会在启动时直接 argparse.ArgumentError，整个测试跑不起来。
    parser.addoption("--pw-trace", action="store_true", default=False,
                     help="录制 Playwright 追踪文件，跑完可在浏览器里逐步回放")
    parser.addoption("--mock", action="store_true", default=False,
                     help="接口用例走本地 mock 服务，断网可跑，可注入故障")


# ===============================================================
# 二、配置对象
# ===============================================================
@pytest.fixture(scope="session")
def run_id():
    """本次执行的唯一批次号。用于隔离截图、台账、基线目录。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# cfg fixture 在 plugins/site_plugin.py：按目录给各站配置，见那边的说明


# ===============================================================
# 三、浏览器管理
#     session 级：整个测试只启动一次浏览器，节省大量时间
# ===============================================================
# profile 目录里这几个是人手放的，不是浏览器生成的，清理时要留着。
# home.html 是桌面快捷方式的落地页，删了手动打开就是一个错误页。
PROFILE_KEEP = {"home.html", "launch.bat", "xray.json"}


def _reset_profile(profile):
    """
    清空浏览器 profile —— 等效无痕。

    为什么不是简单 rmtree 整个目录：
        目录里除了浏览器自己生成的东西，还有人手放进去的 home.html。
        整个删掉，桌面快捷方式下次打开就是 404。
        所以逐项删，白名单里的留下。
    """
    profile.mkdir(parents=True, exist_ok=True)
    for item in profile.iterdir():
        if item.name in PROFILE_KEEP:
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            try:
                item.unlink()
            except OSError:
                pass


@pytest.fixture(scope="session")
def browser_engine(request):
    """本次跑用哪个内核。跨浏览器兼容性用例靠它区分。"""
    return request.config.getoption("--browser-engine")


_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


# 本机端口探测必须绕开代理：环境里配了 HTTP_PROXY 时，urllib 会把
# 127.0.0.1 也发给代理，每次探测都卡满超时，端口明明开着也判成没开。
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _cdp_ready(port):
    try:
        _NO_PROXY.open("http://127.0.0.1:%d/json/version" % port, timeout=2)
        return True
    except Exception:
        return False


def _start_chrome(cfg, profile, port, headless):
    """
    按桌面快捷方式的同一套参数起 Chrome，返回进程。

    同一个 user-data-dir 已经被一个没开端口的 Chrome 占着时，
    chrome.exe 只会把请求交给那个实例然后退出，端口永远不会开 ——
    所以等不到端口要明确报出来，而不是傻等超时。
    """
    args = [cfg.get("chrome_path"), "--remote-debugging-port=%d" % port,
            "--user-data-dir=%s" % profile, "--remote-allow-origins=*",
            "--no-first-run", "--no-default-browser-check", "--lang=en-US",
            "--disable-notifications", "--ignore-certificate-errors",
            "--disable-blink-features=AutomationControlled"]
    if headless:
        # 无头 Chrome 的 UA 带 "HeadlessChrome"，会被站点反爬拦截，换成真实 UA
        args += ["--headless=new", "--user-agent=%s" % _UA]
    elif cfg.get("maximized", True):
        # 最大化，不是 --start-fullscreen：kiosk 全屏会盖住任务栏
        args.append("--start-maximized")
    home = profile / "home.html"
    if home.exists():
        args.append(home.as_uri())
    proc = subprocess.Popen(args)
    for _ in range(30):
        if _cdp_ready(port):
            return proc
        time.sleep(0.5)
    raise RuntimeError("Chrome 的 %d 端口没起来。多半是 %s 已被一个没开端口的 Chrome "
                       "占用，关掉那个窗口再跑。" % (port, profile))


@pytest.fixture(scope="session")
def browser(request, cfg, browser_engine):
    """
    启动浏览器，返回一个 BrowserContext。

    ★ Chromium 用的是本机的 Google Chrome，和桌面快捷方式同一套 ★

        D:/Browser_Test 就是桌面「浏览器/Test」快捷方式那个文件夹。
        以前框架用 Playwright 自带的 Chromium 147 打开它，快捷方式用的是
        本机 Chrome 153 —— 两个版本轮流写同一个 profile，手动打开就不对劲。
        现在和 AI / Script / Stock 几个浏览器一个套路：
            端口 9444 通     → 你开着的 Test 窗口，直接连上去，不清空、不关
            端口不通         → 清空 profile（等效无痕），按快捷方式的参数起 Chrome
            跑完             → 自己起的就关掉；你的窗口只断开连接

    ★ Firefox / WebKit、以及没装 Chrome 的机器（CI）★

        仍用 Playwright 自带内核 + launch_persistent_context，
        profile 放在 reports/ 下各自的目录 —— 绝不能写进 D:/Browser_Test，
        不同内核的 profile 格式不通用，混写会把 Chrome 的 profile 弄坏。

    隔离：全局只有一个 context，没法每条用例新建。所以两层补偿：
        1. 自己起浏览器前清空 profile
        2. 每条用例结束后清 cookie 和 storage（见 context fixture）
    """
    headed = request.config.getoption("--headed")
    slow = request.config.getoption("--slow")
    slow_mo = slow if slow is not None else int(cfg.get("slow_mo", 0))

    # 默认有头，本地写用例时看得见在点什么。
    # 但 CI 服务器没有显示器，headed 会直接启动失败 ——
    # GitHub Actions 等主流 CI 都会设 CI=true，据此自动切回无头。
    force_headless = (request.config.getoption("--headless")
                      or bool(os.environ.get("CI")))
    headless = force_headless or (not headed and cfg.headless)

    chrome = cfg.get("chrome_path")
    use_chrome = browser_engine == "chromium" and chrome and Path(chrome).exists()

    with sync_playwright() as pw:
        proc = None
        if use_chrome:
            port = int(cfg.get("cdp_port", 9444))
            profile = Path(cfg.get("browser_profile"))
            if not _cdp_ready(port):
                _reset_profile(profile)
                proc = _start_chrome(cfg, profile, port, headless)
            b = pw.chromium.connect_over_cdp("http://127.0.0.1:%d" % port, slow_mo=slow_mo)
            ctx = b.contexts[0]
            ctx.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
            log.info("已连上 Chrome (端口 %d, %s, profile=%s)", port,
                     "自己起的" if proc else "你开着的窗口", profile)
        else:
            profile = REPORT_DIR / ("browser_profile_" + browser_engine)
            _reset_profile(profile)
            # 启动参数是 Chromium 专属的，原样传给 firefox / webkit 会直接报错
            args = (["--disable-blink-features=AutomationControlled",
                     "--disable-notifications"]
                    + (["--start-maximized"] if not headless else [])
                    if browser_engine == "chromium" else [])
            ctx = getattr(pw, browser_engine).launch_persistent_context(
                user_data_dir=str(profile), headless=headless, slow_mo=slow_mo,
                args=args, no_viewport=True, ignore_https_errors=True,
                locale="en-US", user_agent=_UA,
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"})
            log.info("浏览器已启动 (%s, headless=%s, profile=%s)",
                     browser_engine, headless, profile)

        ctx.set_default_timeout(cfg.timeout)
        ctx.set_default_navigation_timeout(cfg.nav_timeout)
        yield ctx

        if not use_chrome:
            ctx.close()
        elif proc:
            try:
                b.new_browser_cdp_session().send("Browser.close")
                proc.wait(timeout=10)
            except Exception:
                proc.kill()         # 只杀自己起的这个 PID
        log.info("浏览器已关闭" if (proc or not use_chrome) else "已断开，窗口留着")


@pytest.fixture(scope="function")
def context(request, browser, cfg):
    """
    每条用例拿到的浏览器上下文。

    persistent 模式下全局只有一个 context，没法像以前那样每条用例新建。
    所以隔离靠「用完就地清干净」：cookie 清掉，storage 清掉。
    做不到就会出现最难查的一类问题 —— 用例单独跑过、批量跑挂，
    或者换个执行顺序结果就变了。

    --pw-trace 开启后会录一份完整追踪：
        每一步操作的 DOM 快照、截图、网络请求、控制台输出全在里面。
        跑完用 playwright show-trace 在浏览器里逐步回放，
        比看日志和截图直观得多 —— 相当于给失败现场录了像。
    """
    ctx = browser
    _wipe(ctx)

    tracing = request.config.getoption("--pw-trace")
    if tracing:
        ctx.tracing.start(screenshots=True, snapshots=True, sources=True)

    yield ctx

    if tracing:
        from common.baseline import safe_name
        path = TRACE_DIR / ("%s.zip" % safe_name(request.node.name))
        try:
            ctx.tracing.stop(path=str(path))
            log.info("追踪已保存: %s", path)
        except Exception as exc:
            log.warning("追踪保存失败: %s", exc)

    _wipe(ctx)


def _wipe(ctx):
    """把上一条用例留下的痕迹清掉。清不掉也别让用例挂在这。"""
    try:
        ctx.clear_cookies()
    except Exception as exc:
        log.debug("清 cookie 失败: %s", exc)
    for page in list(ctx.pages):
        try:
            # about:blank 上没有 storage，evaluate 会直接报错，跳过
            if page.url.startswith("http"):
                page.evaluate("() => { localStorage.clear(); "
                              "sessionStorage.clear(); }")
        except Exception as exc:
            log.debug("清 storage 失败: %s", exc)


@pytest.fixture(scope="function")
def page(context):
    p = context.new_page()
    yield p
    # 必须在关页面之前清：localStorage 只能在该站点的页面里清，
    # 页面一关，context 那边的 _wipe 就摸不到它了，购物车会带到下一条用例
    _wipe(context)
    p.close()


# ===============================================================
# 四、失败自动截图（pytest hook）
#
#     这是框架能力的体现，面试可以重点讲：
#     hookwrapper 让我们能拿到用例的执行结果，
#     一旦失败，自动截图 + 贴进 Allure 报告。
#     测试人员写用例时完全不用关心截图这件事。
# ===============================================================
@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    # 只处理「用例执行阶段」的失败，跳过 setup/teardown
    if report.when != "call" or not report.failed:
        return

    page = item.funcargs.get("page")
    if page is None:
        return

    try:
        name = "失败截图_%s" % item.name
        path = SCREENSHOT_DIR / ("%s.png" % item.name)
        page.screenshot(path=str(path), full_page=True)
        allure.attach.file(str(path), name=name,
                           attachment_type=allure.attachment_type.PNG)
        allure.attach(page.url, name="失败时的URL",
                      attachment_type=allure.attachment_type.TEXT)
        log.warning("用例失败，已截图: %s", path)
    except Exception as exc:
        log.warning("失败截图未成功: %s", exc)


# ===============================================================
# 五、执行前后的钩子
# ===============================================================
def pytest_configure(config):
    """执行开始前：清空上一次的 Allure 结果，避免新旧混杂。"""
    allure_dir = config.getoption("--alluredir", None)
    if allure_dir and os.path.exists(allure_dir):
        shutil.rmtree(allure_dir, ignore_errors=True)


def pytest_sessionfinish(session, exitstatus):
    log.info("测试结束，退出码: %s", exitstatus)
