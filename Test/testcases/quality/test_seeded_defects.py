# -*- coding: utf-8 -*-
"""
检测能力验证：我们的检查，到底抓不抓得住缺陷？

★ 这一组用例在测「测试本身」，是整个项目最该讲的一层 ★

    自动化最危险的失效方式不是「用例挂了」，而是**用例永远不会挂**。
    一条断言写松了、选择器选空了、结果没真正比对，
    它会一直显示绿色，而且没有任何迹象告诉你它其实什么都没测。
    这叫「假阴性」，是自动化里最贵的 bug ——
    你以为有 500 条用例守着，实际可能只有 300 条真的在干活。

    所以专业做法是：**给检查器本身做一次对照实验**。
    拿一个「已知有缺陷」的输入喂进去，看它会不会红。
    不会红，说明这个检查是摆设。

    SauceDemo 正好提供了几个故意有缺陷的账号，
    等于给我们准备好了现成的阳性样本：

        standard_user            正常          → 对照组
        problem_user             商品图错乱     → 实验组
        performance_glitch_user  加载被拖慢     → 实验组

    这是软件测试里的「变异测试（Mutation Testing）」思路：
    人为制造一个缺陷，看测试套件能不能发现。
    发现不了，就说明覆盖有洞。

★ 面试价值 ★

    问「你怎么保证你的用例是有效的」，
    大部分人答「我会 review」「我会跑一遍看看」。
    能拿出对照实验的，是完全不同的层级。
"""

import time

import allure
import pytest

from common.assertions import SoftAssert

pytestmark = pytest.mark.seeded


def _image_fingerprints(page, site):
    """
    采集商品图的指纹。

    商品列表里每个商品应该是**不同**的图。
    如果全都指向同一张图，要么是数据坏了，要么是渲染逻辑写错了 ——
    这类缺陷肉眼一看就发现，但传统断言（元素存在、数量正确）
    全都会通过，因为图确实在、数量确实对，只是内容错了。
    """
    return page.eval_on_selector_all(
        site["product_image"],
        "els => els.map(e => (e.getAttribute('src') || '').trim())")


def _distinct_ratio(srcs):
    """不重复图片占比。1.0 = 张张不同，越低说明重复越严重。"""
    if not srcs:
        return 0.0
    return round(len(set(srcs)) / len(srcs), 4)


def _load_seconds(page, cfg, site, logged_in, username):
    """从提交登录到商品列表可见，用户实际等待的秒数。"""
    spec = site["login"]
    page.goto(cfg.base_url + spec["path"], wait_until="domcontentloaded",
              timeout=cfg.nav_timeout)
    page.fill(spec["username_input"], username)
    page.fill(spec["password_input"], cfg.account["password"])

    start = time.time()
    page.click(spec["submit"])
    page.locator(site["product_card"]).first.wait_for(state="visible",
                                                      timeout=60000)
    return round(time.time() - start, 2)


def _require_seeded(site):
    users = site.get("seeded_defect_users")
    if not users:
        pytest.skip("当前被测系统没有可用的「已知缺陷账号」，无法做对照实验")
    return users


@allure.epic("质量属性")
@allure.feature("检测能力验证（对照实验）")
class TestDetectionCapability:

    @allure.story("图片完整性检查")
    @allure.title("SEED_001 - 图片完整性检查应能区分正常账号与故障账号")
    @allure.severity(allure.severity_level.BLOCKER)
    @allure.description(
        "对照实验，两组：\n"
        "  对照组 standard_user  —— 商品图应各不相同\n"
        "  实验组 problem_user   —— Sauce Labs 故意让商品图全部错乱\n\n"
        "两个断言缺一不可：\n"
        "  1. 检查器在正常数据上不能误报（否则天天假警报）\n"
        "  2. 检查器在故障数据上必须报警（否则它就是个摆设）\n\n"
        "只做第 1 条是大多数人的水平；两条都做才叫验证过。"
    )
    @pytest.mark.p0
    def test_image_check_detects_seeded_defect(self, page, cfg, site, logged_in):
        _require_seeded(site)

        with allure.step("对照组：standard_user"):
            logged_in("standard_user")
            page.wait_for_timeout(600)
            good = _image_fingerprints(page, site)
            good_ratio = _distinct_ratio(good)

        with allure.step("实验组：problem_user（已知商品图错乱）"):
            logged_in("problem_user")
            page.wait_for_timeout(600)
            bad = _image_fingerprints(page, site)
            bad_ratio = _distinct_ratio(bad)

        allure.attach(
            "对照组 standard_user：%d 张图，去重后 %d 张，不重复占比 %.0f%%\n"
            "%s\n\n"
            "实验组 problem_user ：%d 张图，去重后 %d 张，不重复占比 %.0f%%\n"
            "%s"
            % (len(good), len(set(good)), good_ratio * 100,
               "\n".join("  " + s[:90] for s in good),
               len(bad), len(set(bad)), bad_ratio * 100,
               "\n".join("  " + s[:90] for s in bad)),
            name="两组商品图指纹对比",
            attachment_type=allure.attachment_type.TEXT)

        sa = SoftAssert()
        sa.true(good_ratio == 1.0,
                "对照组不该误报：standard_user 的商品图应张张不同，"
                "实际不重复占比 %.0f%%" % (good_ratio * 100))
        sa.true(bad_ratio < 1.0,
                "★ 检查器失效 ★ problem_user 的商品图是故意做坏的，"
                "但检查器没发现异常（不重复占比 %.0f%%）。"
                "说明这条检查抓不住真缺陷，是假阴性。" % (bad_ratio * 100))
        sa.assert_all()

    @allure.story("性能预算")
    @allure.title("SEED_002 - 性能预算应能拦下被人为拖慢的账号")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.description(
        "performance_glitch_user 是 Sauce Labs 故意做慢的账号。\n"
        "如果我们的性能预算连这种量级的退化都拦不住，那预算定得就太松了 ——\n"
        "「性能测试永远绿」和「没有性能测试」是一回事。"
    )
    @pytest.mark.p1
    def test_perf_budget_catches_slow_user(self, page, cfg, site, logged_in):
        _require_seeded(site)

        normal = _load_seconds(page, cfg, site, logged_in, "standard_user")
        slow = _load_seconds(page, cfg, site, logged_in,
                             "performance_glitch_user")
        budget_s = cfg.get("perf_budget.lcp_ms", 4000) / 1000.0

        allure.attach(
            "standard_user           登录到商品可见: %.2fs\n"
            "performance_glitch_user 登录到商品可见: %.2fs\n"
            "退化倍数: %.1f×\n"
            "性能预算(LCP): %.2fs"
            % (normal, slow, (slow / normal) if normal else 0, budget_s),
            name="两组加载耗时对比",
            attachment_type=allure.attachment_type.TEXT)

        sa = SoftAssert()
        sa.true(slow > normal,
                "★ 对照实验前提不成立 ★ 故障账号 %.2fs 没有比正常账号 %.2fs 慢，"
                "说明这次测量没测到东西" % (slow, normal))
        sa.true(slow > budget_s,
                "★ 预算太松 ★ 被人为拖慢的账号耗时 %.2fs，"
                "居然还在 %.2fs 的预算之内 —— 这个预算拦不住任何真实退化"
                % (slow, budget_s))
        sa.true(normal <= budget_s,
                "对照组不该误报：正常账号耗时 %.2fs 应在预算 %.2fs 之内"
                % (normal, budget_s))
        sa.assert_all()

    @allure.story("错误处理")
    @allure.title("SEED_003 - 锁定账号应给出明确的错误提示")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.description(
        "locked_out_user 是被锁定的账号。\n"
        "验收标准不只是「登不进去」，还要「告诉用户为什么」——\n"
        "静默失败是最糟糕的错误处理：用户会反复重试，然后来投诉。"
    )
    @pytest.mark.p1
    def test_locked_user_gets_clear_error(self, page, cfg, site):
        spec = site.get("login")
        if not spec:
            pytest.skip("当前被测系统不需要登录")

        page.goto(cfg.base_url + spec["path"], wait_until="domcontentloaded",
                  timeout=cfg.nav_timeout)
        page.fill(spec["username_input"], "locked_out_user")
        page.fill(spec["password_input"], cfg.account["password"])
        page.click(spec["submit"])
        page.wait_for_timeout(1200)

        body = page.inner_text("body")
        allure.attach(body[:800], name="锁定账号登录后的页面文案",
                      attachment_type=allure.attachment_type.TEXT)

        sa = SoftAssert()
        sa.not_contains(page.url, "inventory", "锁定账号不应登录成功")
        sa.true(len(body.strip()) > 20, "页面不应白屏")
        sa.true("locked" in body.lower() or "lock" in body.lower(),
                "应明确告知账号被锁定，实际提示：%s" % body[:200].replace("\n", " "))
        # 错误提示里不能带技术细节，那是信息泄露
        for leak in ("Traceback", "SQL", "Exception", "at java.", "stack"):
            sa.not_contains(body, leak, "错误提示不应泄露技术细节 [%s]" % leak)
        sa.assert_all()
