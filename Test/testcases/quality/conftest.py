# -*- coding: utf-8 -*-
"""
质量属性测试层的共享 fixture。

★ 这一层测什么 ★

    不是「功能对不对」，而是「做得好不好」——
    软件工程里叫非功能需求（Non-Functional Requirements）：
    可访问性、响应式、性能、容错。

    功能测试回答「能不能用」，这一层回答「用起来行不行」。
    真实项目里线上事故很少是「按钮点不了」，
    更多是「手机上排版炸了」「网慢的时候白屏」「广告挂了整站瘫痪」——
    全都落在这一层。

★ 为什么不写死选择器 ★

    这一层的检查逻辑和被测系统无关（「页面不许横向溢出」对谁都成立），
    但验收点是系统专属的。所以选择器、页面清单、要不要登录，
    全部从 sites/<站>/site.yaml 的 profile（适配器）里取。
    换个被测系统 = 加一份适配器，用例一行不用改。
"""

import pytest

from config.site_profile import profile_for


@pytest.fixture(scope="session")
def site(cfg):
    """当前被测系统的适配器。"""
    return profile_for(cfg)


@pytest.fixture(scope="session")
def pages(site):
    """被测页面清单，来自适配器。"""
    return site["pages"]


# 常见设备档位。宽度取自真实机型，不是随便凑的整数。
VIEWPORTS = [
    ("手机", 390, 844),      # iPhone 14
    ("平板", 820, 1180),     # iPad Air 竖屏
    ("笔记本", 1440, 900),
    ("宽屏", 1920, 1080),
]


@pytest.fixture
def logged_in(page, cfg, site):
    """
    按适配器描述的方式登录。站点不需要登录时是个空操作。

    用例层不需要知道「这个站怎么登」——
    输入框叫什么、按钮在哪、登录成功的判据是什么，全在适配器里。
    """
    def _login(username=None, password=None):
        spec = site.get("login")
        if not spec:
            return page
        user = username or cfg.account.get("email")
        pwd = password or cfg.account.get("password")
        page.goto(cfg.base_url + spec["path"],
                  wait_until="domcontentloaded", timeout=cfg.nav_timeout)
        page.fill(spec["username_input"], user)
        page.fill(spec["password_input"], pwd)
        page.click(spec["submit"])
        page.wait_for_url(spec["success_url"], timeout=cfg.nav_timeout)
        page.wait_for_timeout(500)
        return page
    return _login


@pytest.fixture
def goto(page, cfg, site, logged_in):
    """
    打开一个路径并等到页面真正就绪。

    需要登录的站点会自动先登录一次 —— 这一层的用例只关心
    「页面稳定地停在那儿」，不该在每条用例里重复写登录流程。
    """
    state = {"logged_in": False}

    def _goto(path, wait_ms=1200, username=None):
        spec = site.get("login")
        public = path in (site.get("public_pages") or [])
        if spec and not public and (not state["logged_in"] or username):
            logged_in(username)
            state["logged_in"] = True

        url = path if path.startswith("http") else cfg.base_url + path
        page.goto(url, wait_until="domcontentloaded", timeout=cfg.nav_timeout)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            # 挂着广告和统计脚本的站点，networkidle 可能永远等不到。
            # 等不到不算失败，退回固定等待 —— 这一层要的是「渲染完了」，
            # 不是「网络绝对安静」。
            page.wait_for_timeout(wait_ms)
        return page
    return _goto


@pytest.fixture
def console_watch(page):
    """
    收集页面的控制台报错和未捕获异常。

    很多前端缺陷不会让用例失败：页面照样渲染，按钮照样能点，
    但控制台里一堆 TypeError —— 说明有代码路径已经挂了，
    只是恰好没影响到你断言的那部分。这类问题只有主动收集才能看见。
    """
    errors = {"console": [], "pageerror": []}
    page.on("console",
            lambda m: errors["console"].append(m.text[:300])
            if m.type == "error" else None)
    page.on("pageerror", lambda e: errors["pageerror"].append(str(e)[:300]))
    return errors


def pytest_generate_tests(metafunc):
    """
    把适配器里的页面清单动态展开成参数化用例。

    不能用 @parametrize 写死 —— 页面清单是跟着被测系统走的，
    换个站（--site=saucedemo）页面就不一样了。
    参数化必须发生在拿到配置之后，所以要用这个钩子。
    """
    if "page_name" in metafunc.fixturenames and "path" in metafunc.fixturenames:
        from config.settings import get_config
        cfg = get_config(metafunc.config.getoption("--site"), metafunc.config.getoption("--env"))
        pages = profile_for(cfg)["pages"]
        metafunc.parametrize("page_name,path", pages,
                             ids=[p[0] for p in pages])
