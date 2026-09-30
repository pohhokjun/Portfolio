# -*- coding: utf-8 -*-
"""
响应式布局 + 跨浏览器兼容性

★ 为什么单独一层 ★

    功能用例默认跑在 1440×900 的桌面视口上，
    但真实流量一半以上来自手机。桌面全绿、手机炸掉，是最常见的线上事故之一。

    而且这类问题**功能用例永远发现不了**：
    按钮还在、还能点，只是被挤到屏幕外，或者要横向滚动才看得到。
    断言「元素存在」是通过的 —— 这就是为什么必须有专门的布局断言。

★ 核心断言：页面不许横向滚动 ★

    这是响应式最硬的一条指标，也是最容易量化的：
        document.documentElement.scrollWidth > window.innerWidth
    成立就说明有内容溢出了视口。用户体验上表现为
    「要左右拖着看」，在手机上几乎等同于页面坏了。

★ 跨浏览器 ★

    pytest --browser-engine=firefox / webkit
    WebKit 就是 Safari 的内核 —— iPhone 上所有浏览器都被强制用它，
    所以「在 WebKit 上跑一遍」约等于「在 iPhone 上验过」。
"""

import allure
import pytest

from common.assertions import SoftAssert
from testcases.quality.conftest import VIEWPORTS

# 手机档允许的横向溢出像素。完全为 0 太苛刻 ——
# 滚动条宽度、亚像素舍入都会造成 1~2px 的假溢出。
OVERFLOW_TOLERANCE = 3


def _layout_metrics(page):
    return page.evaluate("""() => {
        const d = document.documentElement;
        // 找出具体是谁溢出了，报告里要能直接指到元素，不能只说「有溢出」
        const offenders = [];
        const limit = d.clientWidth;
        document.querySelectorAll('body *').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return;
            const right = r.right + window.scrollX;
            if (right > limit + 3) {
                offenders.push({
                    sel: el.tagName.toLowerCase()
                         + (el.id ? '#' + el.id : '')
                         + (el.className && typeof el.className === 'string'
                            ? '.' + el.className.trim().split(/\\s+/).slice(0,2).join('.')
                            : ''),
                    right: Math.round(right),
                    width: Math.round(r.width),
                });
            }
        });
        offenders.sort((a, b) => b.right - a.right);
        return {
            scrollWidth: d.scrollWidth,
            clientWidth: d.clientWidth,
            innerWidth: window.innerWidth,
            overflow: d.scrollWidth - d.clientWidth,
            offenders: offenders.slice(0, 8),
        };
    }""")


@allure.epic("质量属性")
@allure.feature("响应式布局")
class TestResponsiveLayout:

    @allure.story("横向溢出")
    @allure.title("RESP_001 - {vp_name}({w}x{h}) 下 {page_name} 不应横向溢出")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.responsive
    @pytest.mark.p1
    @pytest.mark.parametrize("vp_name,w,h", VIEWPORTS,
                             ids=["%s%d" % (v[0], v[1]) for v in VIEWPORTS])
    def test_no_horizontal_overflow(self, page, cfg, goto,
                                    vp_name, w, h, page_name, path):
        page.set_viewport_size({"width": w, "height": h})
        goto(path)

        m = _layout_metrics(page)
        allure.attach(
            "视口 %d×%d\n"
            "scrollWidth=%d  clientWidth=%d  溢出=%dpx\n\n%s"
            % (w, h, m["scrollWidth"], m["clientWidth"], m["overflow"],
               "\n".join("  溢出 %4dpx  %s (宽 %d)"
                         % (o["right"] - m["clientWidth"], o["sel"], o["width"])
                         for o in m["offenders"]) or "  （无溢出元素）"),
            name="布局度量_%s_%s" % (vp_name, page_name),
            attachment_type=allure.attachment_type.TEXT)

        assert m["overflow"] <= OVERFLOW_TOLERANCE, (
            "%s 在 %s(%d×%d) 下横向溢出 %dpx，用户需要左右拖动才能看全。\n"
            "溢出最严重的元素：\n%s"
            % (page_name, vp_name, w, h, m["overflow"],
               "\n".join("  - %s（右边缘 %dpx，视口只有 %dpx）"
                         % (o["sel"], o["right"], m["clientWidth"])
                         for o in m["offenders"][:5])))

    @allure.story("触控目标尺寸")
    @allure.title("RESP_002 - 手机视口下可点元素不应小于 24px")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.description(
        "WCAG 2.2 新增的 2.5.8 Target Size (Minimum)：\n"
        "触控目标最小 24×24 CSS 像素。太小的按钮在手机上点不准，\n"
        "对手抖、老年用户尤其明显。Apple 的建议值更高，是 44×44。"
    )
    @pytest.mark.responsive
    @pytest.mark.a11y
    @pytest.mark.p2
    def test_touch_target_size(self, page, goto, site):
        page.set_viewport_size({"width": 390, "height": 844})
        goto(site.get("product_page") or site["pages"][-1][1])

        small = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('a[href], button, [role="button"]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return;       // 不可见的不算
                if (r.width < 24 || r.height < 24) {
                    out.push({
                        text: (el.innerText || '').trim().slice(0, 24),
                        size: Math.round(r.width) + 'x' + Math.round(r.height),
                        html: el.outerHTML.slice(0, 90),
                    });
                }
            });
            return out;
        }""")

        allure.attach(
            "\n".join("%-8s %-24s %s" % (s["size"], s["text"], s["html"])
                      for s in small) or "（全部达标）",
            name="小于 24px 的触控目标",
            attachment_type=allure.attachment_type.TEXT)

        # 记录不阻断：这个站点的页脚有一批小图标链接，属于已知设计取舍。
        # 阻断构建会让这条用例被人直接注释掉，反而什么都留不下。
        allure.dynamic.description(
            "手机视口下发现 %d 个小于 24×24 的触控目标，明细见附件。" % len(small))
        assert len(small) < 60, (
            "手机视口下有 %d 个触控目标小于 24×24，数量已经异常，"
            "说明整体布局在小屏下缩放失控了" % len(small))

    @allure.story("关键内容可见")
    @allure.title("RESP_003 - {vp_name} 下首屏必须能看到主导航和商品入口")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.responsive
    @pytest.mark.p1
    @pytest.mark.parametrize("vp_name,w,h", VIEWPORTS,
                             ids=["%s%d" % (v[0], v[1]) for v in VIEWPORTS])
    def test_key_elements_reachable(self, page, goto, site, vp_name, w, h):
        page.set_viewport_size({"width": w, "height": h})
        goto(site.get("product_page") or site["pages"][-1][1])

        sa = SoftAssert()
        for label, selector in (site.get("nav") or {}).items():
            loc = page.locator(selector).first
            visible = loc.count() > 0 and loc.is_visible()
            sa.true(visible, "%s 在 %s 下应可见" % (label, vp_name))

            if visible:
                box = loc.bounding_box()
                # 元素「存在」不等于「用户看得到」——被挤出视口右侧是很常见的响应式缺陷
                inside = box and box["x"] >= -1 and box["x"] + box["width"] <= w + 1
                sa.true(inside,
                        "%s 在 %s 下应完整落在视口内，实际 x=%s 宽=%s 视口宽=%d"
                        % (label, vp_name,
                           round(box["x"]) if box else "?",
                           round(box["width"]) if box else "?", w))
        sa.assert_all()


@allure.epic("质量属性")
@allure.feature("跨浏览器兼容性")
class TestCrossBrowser:
    """
    同一套断言，换内核跑。

        pytest -m crossbrowser --browser-engine=chromium
        pytest -m crossbrowser --browser-engine=firefox
        pytest -m crossbrowser --browser-engine=webkit

    面试常问「跨浏览器怎么做」，标准答案不是「每个浏览器写一套用例」，
    而是「一套用例，参数化内核」—— 用例是一份，执行是三遍。
    """

    @allure.story("核心页面渲染")
    @allure.title("XB_001 - {page_name} 在当前内核下应正常渲染")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.crossbrowser
    @pytest.mark.p0
    def test_page_renders(self, page, goto, site, browser_engine,
                          console_watch, page_name, path):
        goto(path)

        sa = SoftAssert()
        body = page.inner_text("body")
        sa.true(len(body.strip()) > 50,
                "[%s] %s 页面正文不应为空白" % (browser_engine, page_name))
        marker = (site.get("public_ready_marker")
                  if path in (site.get("public_pages") or [])
                  else site.get("ready_marker"))
        if marker:
            sa.true(page.locator(marker).count() > 0,
                    "[%s] %s 应渲染出就绪标志 %s"
                    % (browser_engine, page_name, marker))

        # 未捕获的 JS 异常在不同内核下差异很大，是跨浏览器缺陷的主要来源
        allure.attach(
            "内核: %s\n控制台错误 %d 条\n未捕获异常 %d 条\n\n%s"
            % (browser_engine, len(console_watch["console"]),
               len(console_watch["pageerror"]),
               "\n".join(console_watch["console"][:10]
                         + console_watch["pageerror"][:10]) or "（无）"),
            name="控制台_%s_%s" % (browser_engine, page_name),
            attachment_type=allure.attachment_type.TEXT)

        sa.true(not console_watch["pageerror"],
                "[%s] %s 不应有未捕获的 JS 异常：%s"
                % (browser_engine, page_name, console_watch["pageerror"][:3]))
        sa.assert_all()
