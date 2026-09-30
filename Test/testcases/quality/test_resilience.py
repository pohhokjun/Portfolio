# -*- coding: utf-8 -*-
"""
容错测试：故障注入（Fault Injection）

★ 这一层是高级测试工程师和普通执行者最明显的分水岭 ★

    普通做法：在一切正常的环境里，验证功能正常。
    问题：线上事故几乎全部发生在「不正常」的时候 ——
          第三方挂了、网变慢了、CDN 抽风了、图片 404 了。
          这些场景在正常环境里**永远不会自然出现**，只能主动制造。

    Playwright 的 page.route 能在浏览器和网络之间插一层，
    让你精确决定「哪个请求要坏，怎么坏」。
    这就是混沌工程（Chaos Engineering）在前端的落地方式。

★ 一个重要的自我约束 ★

    只注入「让真实资源坏掉」的故障，不伪造响应内容。
    如果我自己 fulfill 一段假 HTML 再去断言它，那测的是我写的 mock，
    不是被测系统 —— 这是故障注入最容易走偏的地方。
"""

import time

import allure
import pytest

from common.assertions import SoftAssert
from config.settings import SCREENSHOT_DIR

IMAGE_GLOB = "**/*.{png,jpg,jpeg,gif,webp,svg}"


def _shot(page, name):
    """截图并挂进报告。容错用例的证据主要靠图 —— 页面坏没坏，一眼就看出来。"""
    path = SCREENSHOT_DIR / ("容错_%s.png" % name)
    page.screenshot(path=str(path), full_page=False)
    allure.attach.file(str(path), name=name,
                       attachment_type=allure.attachment_type.PNG)
    return path


@allure.epic("质量属性")
@allure.feature("容错与故障注入")
class TestResilience:

    @allure.story("第三方依赖失效")
    @allure.title("FAULT_001 - 广告与统计脚本全挂时，主功能仍应可用")
    @allure.severity(allure.severity_level.BLOCKER)
    @allure.description(
        "把适配器里登记的第三方域名请求全部 abort，模拟它们宕机或被墙。\n\n"
        "这是最值得写的一条容错用例：\n"
        "  · 国内访问境外统计脚本超时，是极其常见的真实场景\n"
        "  · 广告脚本挂掉导致整站白屏的事故每年都有\n"
        "  · 本项目排查过的问题已经证明第三方内容会遮挡按钮、干扰视觉基线，\n"
        "    说明它对被测系统的影响是真实存在的\n\n"
        "验收标准：主内容出得来、不白屏、没有页面级未捕获异常。"
    )
    @pytest.mark.resilience
    @pytest.mark.p0
    def test_survives_third_party_outage(self, page, cfg, site,
                                         goto, console_watch):
        blocked = []

        def kill(route, request):
            blocked.append(request.url[:110])
            route.abort()

        patterns = site.get("third_party") or []
        if not patterns:
            pytest.skip("适配器没有登记第三方域名，无从注入")
        for pattern in patterns:
            page.route(pattern, kill)

        goto(site.get("product_page") or site["pages"][-1][1])

        sa = SoftAssert()
        cards = page.locator(site["product_card"]).count()
        sa.true(cards > 0, "第三方全挂时，主内容仍应渲染，实际 %d 项" % cards)
        sa.true(len(page.inner_text("body").strip()) > 200,
                "第三方全挂时，页面不应白屏")
        sa.true(not console_watch["pageerror"],
                "第三方全挂不应引发页面级未捕获异常：%s"
                % console_watch["pageerror"][:3])

        allure.attach(
            "已阻断 %d 个第三方请求\n\n%s\n\n主内容项数: %d\n未捕获异常: %d"
            % (len(blocked), "\n".join("  " + b for b in blocked[:25]) or "  （无）",
               cards, len(console_watch["pageerror"])),
            name="被阻断的第三方请求",
            attachment_type=allure.attachment_type.TEXT)
        _shot(page, "第三方全挂")
        sa.assert_all()

    @allure.story("样式加载失败")
    @allure.title("FAULT_002 - CSS 全部加载失败时，内容仍应可读")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.description(
        "渐进增强（Progressive Enhancement）的基本检查：\n"
        "样式只负责好看，内容和结构必须独立于样式存在。\n"
        "CSS 挂掉时页面会很丑，但文字要读得到、链接要点得着 ——\n"
        "这同时也是屏幕阅读器用户实际感受到的页面。"
    )
    @pytest.mark.resilience
    @pytest.mark.p2
    def test_readable_without_css(self, page, site, goto):
        # 先登录再断样式：登录流程本身不是这条用例的被测对象
        goto(site.get("product_page") or site["pages"][-1][1])

        page.route("**/*.css", lambda route: route.abort())
        page.route("**/*.css?*", lambda route: route.abort())
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        text = page.inner_text("body")
        links = page.locator("a[href]").count()
        buttons = page.locator("button").count()
        _shot(page, "无CSS")

        sa = SoftAssert()
        sa.true(len(text.strip()) > 200,
                "没有样式表时正文仍应可读，实际长度 %d" % len(text.strip()))
        sa.true(links + buttons > 3,
                "没有样式表时可交互元素仍应存在，实际 链接%d + 按钮%d"
                % (links, buttons))
        sa.assert_all()

    @allure.story("图片失效")
    @allure.title("FAULT_003 - 图片全部加载失败时应有 alt 文本兜底")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.description(
        "图片挂掉是最常见的线上问题（CDN 故障、防盗链、路径写错）。\n"
        "alt 是唯一的兜底：图片显示不出来时浏览器显示 alt，\n"
        "屏幕阅读器读的也是 alt。没有 alt 的图片挂掉后就是一个纯粹的空洞。"
    )
    @pytest.mark.resilience
    @pytest.mark.a11y
    @pytest.mark.p2
    def test_images_have_alt_fallback(self, page, site, goto):
        goto(site.get("product_page") or site["pages"][-1][1])

        page.route(IMAGE_GLOB, lambda route: route.fulfill(status=404, body=""))
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        stats = page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('img'));
            const noAlt = imgs.filter(i => !i.getAttribute('alt'));
            return {
                total: imgs.length,
                noAlt: noAlt.length,
                samples: noAlt.slice(0, 8).map(i => i.outerHTML.slice(0, 110)),
            };
        }""")

        _shot(page, "图片全挂")
        allure.attach(
            "图片总数 %d，缺 alt %d\n\n%s"
            % (stats["total"], stats["noAlt"],
               "\n".join("  " + s for s in stats["samples"]) or "  （全部有 alt）"),
            name="缺少 alt 的图片",
            attachment_type=allure.attachment_type.TEXT)

        assert stats["noAlt"] == 0, (
            "有 %d/%d 张图片没有 alt 属性。图片加载失败时这些位置会完全空白，"
            "屏幕阅读器用户也读不到任何信息。\n示例：\n%s"
            % (stats["noAlt"], stats["total"],
               "\n".join("  - %s" % s for s in stats["samples"])))

    @allure.story("断网")
    @allure.title("FAULT_004 - 断网再恢复后应能正常继续使用")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.description(
        "移动端最真实的场景：地铁进隧道、电梯里、切换 WiFi。\n"
        "验收标准不是「断网时还能用」（那不可能），\n"
        "而是「恢复后能正常继续，不会卡在某个半坏的中间态」。"
    )
    @pytest.mark.resilience
    @pytest.mark.p1
    def test_recovers_after_offline(self, page, context, cfg, site, goto):
        target = site.get("product_page") or site["pages"][-1][1]
        goto(target)
        assert page.locator(site["product_card"]).count() > 0, "前置条件：主内容正常"

        with allure.step("断网，此时导航应当失败"):
            context.set_offline(True)
            offline_failed = False
            try:
                page.goto(cfg.base_url + target,
                          wait_until="domcontentloaded", timeout=8000)
            except Exception as exc:
                offline_failed = True
                allure.attach(str(exc)[:400], name="断网时的导航错误",
                              attachment_type=allure.attachment_type.TEXT)
            _shot(page, "断网中")
            # 断网了还能成功，说明被 Service Worker 或缓存兜住了 ——
            # 那是好事，不该判失败。这里只如实记录行为。
            allure.attach("断网导航是否失败: %s" % offline_failed,
                          name="断网行为",
                          attachment_type=allure.attachment_type.TEXT)

        with allure.step("恢复网络，应能正常继续"):
            context.set_offline(False)
            page.goto(cfg.base_url + target,
                      wait_until="domcontentloaded", timeout=cfg.nav_timeout)
            page.wait_for_timeout(1500)

        cards = page.locator(site["product_card"]).count()
        _shot(page, "断网恢复后")
        assert cards > 0, (
            "网络恢复后主内容没能重新加载出来（%d 项），"
            "说明应用卡在了断网时的中间态" % cards)

    @allure.story("慢网络")
    @allure.title("FAULT_005 - 图片变慢时，主内容不应被拖住")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.description(
        "给所有图片请求加 800ms 延迟，模拟弱网。\n"
        "验证点：主内容不被图片拖住 —— 也就是图片没有阻塞关键渲染路径。\n"
        "如果这条挂了，说明页面把非关键资源放在了关键路径上。"
    )
    @pytest.mark.resilience
    @pytest.mark.p2
    def test_usable_on_slow_network(self, page, cfg, site, goto):
        target = site.get("product_page") or site["pages"][-1][1]
        goto(target)   # 先完成登录等前置

        def slow(route):
            time.sleep(0.8)
            route.continue_()

        page.route(IMAGE_GLOB, slow)

        start = time.time()
        page.reload(wait_until="domcontentloaded")
        page.locator(site["product_card"]).first.wait_for(
            state="attached", timeout=25000)
        elapsed = round((time.time() - start) * 1000)

        allure.attach(
            "图片全部延迟 800ms 的情况下，主内容 DOM 就绪耗时 %dms" % elapsed,
            name="慢网络耗时", attachment_type=allure.attachment_type.TEXT)

        assert elapsed < 20000, (
            "图片慢的时候，主内容用了 %dms 才就绪，说明图片阻塞了主内容渲染"
            % elapsed)
