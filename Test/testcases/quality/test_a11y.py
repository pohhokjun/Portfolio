# -*- coding: utf-8 -*-
"""
可访问性测试（Accessibility / a11y）

★ 为什么这一层值钱 ★

    可访问性是「残障用户能不能用」，但它的实际影响远不止于此：
        - 欧盟 EAA、美国 ADA、中国信创无障碍标准都有强制要求，
          做不好是**法律风险**，不是体验问题
        - 大厂（尤其外企、出海产品）招测试必问
        - 大部分 a11y 缺陷同时也是 SEO 缺陷和自动化定位难题 ——
          没有 label 的输入框，屏幕阅读器读不出来，
          你写自动化用例也只能靠 xpath 硬定位

    用的是 axe-core，Deque 出的引擎，业界事实标准，
    Chrome DevTools 的 Lighthouse 无障碍评分底层用的也是它。

★ 断言策略：分级，不是一刀切 ★

    axe 把违规分四级：critical / serious / moderate / minor。
    对一个已经上线的站点，把 minor 也判失败没有意义 ——
    第一次跑就会红一片，然后所有人开始忽略它。

    这里只对 critical 判失败，其余全部记录进报告。
    这是引入质量门禁的标准做法：先卡住最严重的，再逐级收紧。
"""

import json

import allure
import pytest

from axe_playwright_python.sync_playwright import Axe


# WCAG 2.1 AA —— 国际通行的合规基线
WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]

# 只有这一级判失败，其余记录不阻断
BLOCKING_IMPACTS = {"critical"}

_axe = Axe()


def _form_page(site):
    """
    挑一个「有表单的页面」来测表单相关的无障碍问题。

    不同站点的表单页路径不一样：有的是 /login，有的登录页就是首页。
    需要登录的站点直接用登录页 —— 那本来就是全站表单最集中的地方。
    """
    spec = site.get("login")
    if spec:
        return spec["path"]
    for name, path in site["pages"]:
        if "登录" in name or "注册" in name:
            return path
    return site["pages"][0][1]


def _first_nav(site):
    """
    取一个「用键盘应该能走到」的主导航目标。

    返回 (标签, 选择器)。适配器里没配导航就返回 None，用例会跳过。
    """
    nav = site.get("nav") or {}
    for label, selector in nav.items():
        return label, selector
    return None


def _run_axe(page):
    """跑一遍扫描，返回按严重级分好组的违规项。"""
    results = _axe.run(page, options={
        "runOnly": {"type": "tag", "values": WCAG_TAGS},
        "resultTypes": ["violations"],
    })
    violations = results.response.get("violations", [])
    by_impact = {}
    for v in violations:
        by_impact.setdefault(v.get("impact") or "unknown", []).append(v)
    return violations, by_impact


def _attach(name, violations, by_impact):
    """把扫描结果贴进 Allure。报告要能直接拿去提 bug，不用重跑。"""
    summary = "  ".join("%s=%d" % (k, len(v)) for k, v in sorted(by_impact.items()))
    lines = ["页面: %s" % name, "违规项统计: %s" % (summary or "无"), ""]
    for v in violations:
        nodes = v.get("nodes", [])
        lines.append("[%s] %s" % ((v.get("impact") or "?").upper(), v.get("id")))
        lines.append("  说明: %s" % v.get("help"))
        lines.append("  规则: %s" % v.get("helpUrl", ""))
        lines.append("  命中 %d 处，示例元素：" % len(nodes))
        for n in nodes[:3]:
            lines.append("    %s" % "".join(n.get("target", []))[:160])
            lines.append("      %s" % (n.get("html", "")[:160]))
        lines.append("")
    allure.attach("\n".join(lines), name="无障碍扫描明细_%s" % name,
                  attachment_type=allure.attachment_type.TEXT)
    allure.attach(json.dumps(by_impact and
                             {k: [v["id"] for v in vs] for k, vs in by_impact.items()},
                             ensure_ascii=False, indent=2),
                  name="违规规则清单_%s" % name,
                  attachment_type=allure.attachment_type.JSON)


@allure.epic("质量属性")
@allure.feature("可访问性 WCAG 2.1 AA")
class TestAccessibility:

    @allure.story("整页合规扫描")
    @allure.title("A11Y_001 - {page_name} 不应存在 critical 级无障碍缺陷")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.a11y
    @pytest.mark.p1
    def test_no_critical_violations(self, goto, page, site, page_name, path):
        goto(path)
        violations, by_impact = _run_axe(page)
        _attach(page_name, violations, by_impact)

        blocking = [v for v in violations
                    if (v.get("impact") or "") in BLOCKING_IMPACTS]

        # 命中已知缺陷登记表的，标成 xfail 而不是 fail：
        # 缺陷是被跟踪的，不是被放过的。详见 config/site_profile.py 的说明。
        known = site.get("known_defects") or {}
        hit = [v["id"] for v in blocking if v["id"] in known]
        if hit and len(hit) == len(blocking):
            pytest.xfail("；".join(known[i] for i in hit))

        assert not blocking, (
            "%s 存在 %d 条 critical 级无障碍缺陷：\n%s"
            % (page_name, len(blocking),
               "\n".join("  - %s : %s" % (v["id"], v.get("help"))
                         for v in blocking)))

    @allure.story("表单可用性")
    @allure.title("A11Y_002 - 登录注册页每个输入框都应有可编程的名称")
    @allure.severity(allure.severity_level.CRITICAL)
    @allure.description(
        "输入框没有 label / aria-label / placeholder 的后果：\n"
        "  1. 屏幕阅读器只会念「编辑框」，用户不知道该填什么\n"
        "  2. 自动化用例也定位不到语义，只能靠 xpath 硬写，页面一改就挂\n"
        "这条同时是无障碍缺陷和可测试性缺陷。"
    )
    @pytest.mark.a11y
    @pytest.mark.p1
    def test_form_inputs_have_names(self, goto, page, site):
        goto(_form_page(site))

        nameless = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll(
                'input:not([type=hidden]):not([type=submit]), textarea, select'
            ).forEach(el => {
                const byLabel = el.labels && el.labels.length > 0;
                const named = byLabel
                    || el.getAttribute('aria-label')
                    || el.getAttribute('aria-labelledby')
                    || el.getAttribute('placeholder')
                    || el.getAttribute('title');
                if (!named) {
                    out.push({
                        tag: el.tagName.toLowerCase(),
                        type: el.type || '',
                        name: el.name || '',
                        id: el.id || '',
                        outer: el.outerHTML.slice(0, 120),
                    });
                }
            });
            return out;
        }""")

        allure.attach(json.dumps(nameless, ensure_ascii=False, indent=2),
                      name="没有可编程名称的控件",
                      attachment_type=allure.attachment_type.JSON)

        assert not nameless, (
            "登录注册页有 %d 个输入框没有任何可编程名称：\n%s"
            % (len(nameless),
               "\n".join("  - %s" % n["outer"] for n in nameless)))

    @allure.story("键盘可达性")
    @allure.title("A11Y_003 - 主导航应能纯键盘操作")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.description(
        "不用鼠标，连续按 Tab 能不能走到主导航并回车进入。\n"
        "键盘可达是无障碍的底线：肢体障碍用户、屏幕阅读器用户全靠它。"
    )
    @pytest.mark.a11y
    @pytest.mark.p2
    def test_keyboard_navigation(self, goto, page, site):
        target = _first_nav(site)
        if not target:
            pytest.skip("适配器没有配置主导航，跳过键盘可达性检查")
        label, selector = target

        # 从商品页开始 —— 主导航在这类内容页上一定存在
        goto(site.get("product_page") or site["pages"][-1][1])

        reached = []
        hit = False
        for _ in range(30):
            page.keyboard.press("Tab")
            info = page.evaluate("""(sel) => {
                const el = document.activeElement;
                if (!el || el === document.body) return null;
                // 焦点元素本身是目标，或者落在目标内部，都算走到了
                const t = document.querySelector(sel);
                return {
                    tag: el.tagName.toLowerCase(),
                    text: (el.innerText || el.value || '').trim().slice(0, 40),
                    isTarget: !!(t && (t === el || t.contains(el) || el.contains(t))),
                };
            }""", selector)
            if info:
                reached.append(info)
                if info["isTarget"]:
                    hit = True
                    break

        allure.attach(
            "目标: %s  (%s)\n\n%s"
            % (label, selector,
               "\n".join("%2d. <%s> %s%s"
                         % (i + 1, r["tag"], r["text"],
                            "   ← 命中目标" if r["isTarget"] else "")
                         for i, r in enumerate(reached))),
            name="Tab 键的焦点路径",
            attachment_type=allure.attachment_type.TEXT)

        if not hit:
            known = (site.get("known_defects") or {}).get("keyboard-cart")
            if known:
                pytest.xfail(known)
        assert hit, (
            "连按 30 次 Tab 也没走到主导航「%s」(%s)。\n"
            "键盘用户无法到达主导航就等于站点不可用。焦点路径见报告附件。"
            % (label, selector))

    @allure.story("焦点可见性")
    @allure.title("A11Y_004 - 键盘焦点必须看得见")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.description(
        "很多站点为了「好看」写了 outline:none，把焦点框去掉了。\n"
        "结果用键盘操作时完全不知道现在选中的是哪个元素 —— 等于不可用。\n"
        "WCAG 2.4.7 Focus Visible 明确要求焦点必须有可见指示。"
    )
    @pytest.mark.a11y
    @pytest.mark.p2
    def test_focus_is_visible(self, goto, page, site):
        goto(_form_page(site))

        # ★ 断言「效果」，不要断言「实现」 ★
        #
        #   第一版只看 outline 和 box-shadow：两个都没有就判违规。
        #   这个写法的问题是它在猜「开发会用哪个 CSS 属性做焦点样式」——
        #   实际上改边框色、改背景、加下划线都是合法的焦点指示，
        #   猜漏一个就会误报，猜多了又会漏报。
        #
        #   现在的写法：对同一个元素取「聚焦前」和「聚焦后」的计算样式，
        #   只要有任何一项变了，就说明焦点看得见。
        #   不关心用什么实现，只关心用户能不能看出来。
        #
        #   顺带一提：换成这个更严谨的写法之后，SauceDemo 登录页
        #   那三个控件依然判为违规 —— 8 项属性零变化，是真缺陷。
        invisible = page.evaluate("""() => {
            const WATCH = ['outlineStyle', 'outlineWidth', 'outlineColor',
                           'boxShadow', 'borderColor', 'borderWidth',
                           'backgroundColor', 'color', 'textDecorationLine'];
            const snap = el => {
                const s = getComputedStyle(el);
                return WATCH.map(k => s[k]).join('|');
            };
            const out = [];
            const targets = document.querySelectorAll(
                'a[href], button, input:not([type=hidden]), select, textarea');
            for (const el of Array.from(targets).slice(0, 40)) {
                el.blur();
                const before = snap(el);
                el.focus();
                const after = snap(el);
                if (before === after) {
                    out.push({html: el.outerHTML.slice(0, 100), style: after});
                }
                el.blur();
            }
            return out.map(o => o.html);
        }""")

        allure.attach("\n".join(invisible) or "（全部元素聚焦时都有可见指示）",
                      name="聚焦时没有任何可见指示的元素",
                      attachment_type=allure.attachment_type.TEXT)

        if invisible:
            known = (site.get("known_defects") or {}).get("focus-visible")
            if known:
                pytest.xfail(known)
        assert not invisible, (
            "有 %d 个可交互元素聚焦时没有任何可见指示（WCAG 2.4.7）：\n%s"
            % (len(invisible), "\n".join("  - %s" % h for h in invisible[:8])))
