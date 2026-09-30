# -*- coding: utf-8 -*-
"""
安卓手机模拟测试

★ 为什么是模拟、为什么只有安卓 ★

    手上只有一台 Windows 电脑，没有真机、没有 Mac。
    安卓上的 Chrome 用的就是 Chromium 内核，所以在电脑上用 Chromium
    把「手机该有的东西」都模拟出来，能覆盖大部分手机网页问题：
        屏幕尺寸 + 像素密度      排版在窄屏、高分屏下会不会炸
        mobile 标志 + UA         站点会不会切到手机版
        触屏                     手指点击和鼠标点击走的是两套事件
        横竖屏                   转一下手机，排版还在不在
        弱网                     3G 下首屏多久能用
    苹果（Safari/WebKit）没法在这台机器上等效验证，所以不做。
    真机才有的问题（发热、内存杀后台、厂商 ROM 差异）模拟覆盖不到，报告里要写明。

★ 为什么走 CDP 而不是 Playwright 的 devices ★

    框架用的是 launch_persistent_context，全局只有一个 context，
    而 devices 预设（is_mobile / has_touch）只能在建 context 时给。
    所以直接用 Chrome DevTools Protocol 对单个页面下指令，
    效果一样，用例结束页面关掉，模拟也跟着消失，不会污染后面的用例。
    机型参数照抄 Playwright 自带的设备表。

跑法：
    pytest testcases/quality/test_android.py --site=saucedemo -v
"""

import time
from types import SimpleNamespace

import allure
import pytest

from testcases.quality.test_responsive import OVERFLOW_TOLERANCE, _layout_metrics

pytestmark = [pytest.mark.android, pytest.mark.responsive]

_UA = ("Mozilla/5.0 (Linux; Android %s) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/147.0.7727.15 Mobile Safari/537.36")

# 一台主流大屏、一台 320 宽的窄屏 —— 窄屏最容易把排版挤炸
ANDROID = {
    "Pixel 7": dict(ua=_UA % "14; Pixel 7", w=412, h=839, dpr=2.625),
    "Galaxy S9+": dict(ua=_UA % "8.0.0; SM-G965U Build/R16NW", w=320, h=658, dpr=4.5),
}

# 3G 首屏预算。Chrome DevTools 的「Slow 3G」档：400ms 延迟、约 400kbps
SLOW_3G = {"offline": False, "latency": 400,
           "downloadThroughput": 400 * 1024 / 8, "uploadThroughput": 400 * 1024 / 8}
SLOW_3G_BUDGET_S = 20


def _metrics(dev, landscape=False):
    w, h = (dev.h, dev.w) if landscape else (dev.w, dev.h)
    dev.cdp.send("Emulation.setDeviceMetricsOverride", {
        "width": w, "height": h, "deviceScaleFactor": dev.dpr, "mobile": True,
        "screenOrientation": {"type": "landscapePrimary" if landscape else "portraitPrimary",
                              "angle": 90 if landscape else 0}})


@pytest.fixture(params=list(ANDROID))
def android(request, page, browser_engine):
    if browser_engine != "chromium":
        pytest.skip("安卓 Chrome 是 Chromium 内核，只在 chromium 下模拟才有意义")
    dev = SimpleNamespace(name=request.param, page=page,
                          cdp=page.context.new_cdp_session(page), **ANDROID[request.param])
    _metrics(dev)
    dev.cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
    dev.cdp.send("Emulation.setUserAgentOverride", {"userAgent": dev.ua, "platform": "Android"})
    allure.dynamic.parameter("机型", dev.name)
    return dev


def tap(dev, selector):
    """
    真正的触摸事件：touchStart + touchEnd，由浏览器自己合成 click。
    page.click 发的是鼠标事件，只监听 touch 的按钮用它点是点不出问题的。
    """
    loc = dev.page.locator(selector).first
    loc.scroll_into_view_if_needed()
    b = loc.bounding_box()
    pt = [{"x": b["x"] + b["width"] / 2, "y": b["y"] + b["height"] / 2}]
    dev.cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": pt})
    dev.cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


@allure.epic("质量属性")
@allure.feature("安卓手机")
class TestAndroid:

    @allure.title("AND_001 - 模拟生效：UA / 视口 / 像素密度 / 触屏")
    @allure.description(
        "先证明「手机」真的是手机，后面的用例才有意义。\n"
        "模拟没生效时其他用例照样会绿 —— 测的其实是桌面版，这是最隐蔽的假阳性。")
    @pytest.mark.p0
    def test_emulation_active(self, android, cfg):
        android.page.goto(cfg.base_url, wait_until="domcontentloaded")
        env = android.page.evaluate("""() => ({ua: navigator.userAgent,
            w: window.innerWidth, dpr: window.devicePixelRatio,
            coarse: matchMedia('(pointer: coarse)').matches,
            touch: navigator.maxTouchPoints})""")
        allure.attach(str(env), name="浏览器环境")
        assert "Android" in env["ua"], env
        assert env["w"] == android.w, env
        assert env["dpr"] == android.dpr, env
        assert env["coarse"] and env["touch"] > 0, "触屏没有生效: %s" % env

    @allure.title("AND_002 - 全程手指操作：登录 → 加购 → 进购物车")
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_touch_flow(self, android, cfg, site):
        # 流程全部从适配器拿：要不要登录、加购成功长什么样、购物车在哪。
        # 以前这里写死了 SauceDemo 的元素，换个站就必挂 —— 那是在测「这个站」，不是在测「手机上能不能买」
        need = ["product_card", "add_to_cart", "added_marker", "cart_link", "cart_url", "cart_item"]
        missing = [k for k in need if not site.get(k)]
        if missing:
            pytest.skip("站点适配器没配购物流程字段：%s" % missing)
        p, spec = android.page, site.get("login")
        if spec:
            p.goto(cfg.base_url + spec["path"], wait_until="domcontentloaded")
            p.fill(spec["username_input"], cfg.account["email"])
            p.fill(spec["password_input"], cfg.account["password"])
            tap(android, spec["submit"])
            p.wait_for_url(spec["success_url"])
        else:
            p.goto(cfg.base_url + site["product_page"], wait_until="domcontentloaded")
        # 刚跳转过来列表还在渲染，点早了事件会落空。等列表就绪再点，
        # 点完等「加购成功」的标志出现 —— 状态真的变了才算点中，不能点完就走
        p.locator(site["product_card"]).first.wait_for()
        tap(android, site["add_to_cart"])
        p.locator(site["added_marker"]).first.wait_for(timeout=5000)
        tap(android, site["cart_link"])
        # 只等 DOM 好：有广告的站 load 事件要等所有第三方脚本，可能永远等不到
        p.wait_for_url(site["cart_url"], wait_until="domcontentloaded")
        # URL 变了不等于列表渲染完了，count() 不会等，先等第一件出来再数
        p.locator(site["cart_item"]).first.wait_for(timeout=5000)
        assert p.locator(site["cart_item"]).count() == 1, "购物车里应有 1 件商品"

    @allure.title("AND_003 - {orient} 商品列表不横向溢出")
    @pytest.mark.p1
    @pytest.mark.parametrize("orient", ["竖屏", "横屏"])
    def test_orientation(self, android, goto, site, orient):
        goto(site["product_page"])
        _metrics(android, landscape=orient == "横屏")
        android.page.wait_for_timeout(500)          # 等重排
        m = _layout_metrics(android.page)
        allure.attach(str(m), name="布局度量")
        assert m["overflow"] <= OVERFLOW_TOLERANCE, (
            "%s %s 溢出 %dpx：%s" % (android.name, orient, m["overflow"],
                                   [o["sel"] for o in m["offenders"][:3]]))
        assert android.page.locator(site["product_card"]).first.is_visible()

    @allure.title("AND_004 - Slow 3G 下登录页 %d 秒内可用" % SLOW_3G_BUDGET_S)
    @allure.description(
        "关掉缓存 + 限速到 Slow 3G，从发起请求计时到登录按钮可见。\n"
        "办公室网速永远是好的，用户在地铁里用的是 3G。")
    @pytest.mark.vitals
    @pytest.mark.p1
    def test_slow_3g(self, android, cfg, site):
        cdp = android.cdp
        cdp.send("Network.enable")
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        cdp.send("Network.emulateNetworkConditions", SLOW_3G)
        t0 = time.time()
        android.page.goto(cfg.base_url, wait_until="commit",
                          timeout=SLOW_3G_BUDGET_S * 3000)
        android.page.wait_for_selector(site["public_ready_marker"], state="visible",
                                       timeout=SLOW_3G_BUDGET_S * 3000)
        cost = round(time.time() - t0, 1)
        allure.attach("%s 秒" % cost, name="Slow 3G 首屏可用耗时")
        assert cost <= SLOW_3G_BUDGET_S, "Slow 3G 下 %s 秒才可用，预算 %d 秒" % (
            cost, SLOW_3G_BUDGET_S)
