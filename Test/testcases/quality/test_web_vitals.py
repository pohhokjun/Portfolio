# -*- coding: utf-8 -*-
"""
前端性能：Core Web Vitals 与性能预算

★ 和 sites/*/tests/perf/ 的区别（面试会问） ★

    sites/*/tests/perf/ 测的是**接口**耗时 —— 服务端快不快
    这一层           测的是**用户感知**耗时 —— 页面「看起来」快不快

    两者经常背离：接口 80ms 返回，但首屏 4 秒才画出来，
    因为阻塞渲染的 CSS/JS 太多、图片没压缩、字体加载卡住。
    只测接口的话，这类问题一条都发现不了。

★ Core Web Vitals 是什么 ★

    Google 定的三个用户体验核心指标，直接影响搜索排名：

    | 指标 | 含义              | 好   | 需改进  | 差    |
    |------|-------------------|------|---------|-------|
    | LCP  | 最大内容绘制      | ≤2.5s| 2.5–4s  | >4s   |
    | CLS  | 累计布局偏移      | ≤0.1 | 0.1–0.25| >0.25 |
    | INP  | 交互到下次绘制    | ≤200ms|200-500ms|>500ms|

    这里测 LCP 和 CLS（INP 需要真实用户交互，实验室环境测不准，
    用 TBT 或首次输入延迟近似，本层用 FCP + TTFB 补充）。

★ 性能预算（Performance Budget） ★

    光采集数据没用，必须定阈值并且卡住。
    预算默认写在 config/defaults.yaml 的 perf_budget 段，站点的 site.yaml 可以给不同标准。
    这是「性能测试」和「性能监控」的分界：前者会失败，后者只画图。

★ 注意：LCP / CLS 是 Chromium 专属 API ★

    Firefox 和 WebKit 没有实现 PerformanceObserver 的这两类 entry，
    所以这组用例只在 chromium 下跑，其他内核自动跳过。
    这本身就是一个值得知道的跨浏览器事实。
"""

import allure
import pytest

from common.assertions import SoftAssert

# 采集脚本：注入后等页面稳定，再把三类指标一起读出来
COLLECT_JS = """
() => new Promise(resolve => {
    const out = {lcp: null, cls: 0, fcp: null, ttfb: null,
                 domContentLoaded: null, load: null, transferKB: null};

    const nav = performance.getEntriesByType('navigation')[0];
    if (nav) {
        out.ttfb = Math.round(nav.responseStart);
        out.domContentLoaded = Math.round(nav.domContentLoadedEventEnd);
        out.load = Math.round(nav.loadEventEnd);
    }
    const fcp = performance.getEntriesByName('first-contentful-paint')[0];
    if (fcp) out.fcp = Math.round(fcp.startTime);

    // 传输量：图片没压缩、打包没拆分，都会在这里露出来
    let bytes = 0;
    performance.getEntriesByType('resource').forEach(r => {
        bytes += r.transferSize || 0;
    });
    out.transferKB = Math.round(bytes / 1024);

    try {
        new PerformanceObserver(list => {
            const e = list.getEntries();
            if (e.length) out.lcp = Math.round(e[e.length - 1].startTime);
        }).observe({type: 'largest-contentful-paint', buffered: true});

        new PerformanceObserver(list => {
            for (const entry of list.getEntries()) {
                // 用户主动交互后 0.5 秒内的位移不算数（是用户自己点出来的）
                if (!entry.hadRecentInput) out.cls += entry.value;
            }
        }).observe({type: 'layout-shift', buffered: true});
    } catch (e) {
        out.unsupported = String(e);
    }

    // 给 observer 一点时间把 buffered 的记录吐出来
    setTimeout(() => {
        out.cls = Math.round(out.cls * 10000) / 10000;
        resolve(out);
    }, 1200);
})
"""


def _budget(cfg):
    """性能预算。配置里没写就用 Google 的「良好」标准。"""
    b = cfg.get("perf_budget", {}) or {}
    return {
        "lcp_ms": int(b.get("lcp_ms", 4000)),
        "cls": float(b.get("cls", 0.25)),
        "fcp_ms": int(b.get("fcp_ms", 3000)),
        "ttfb_ms": int(b.get("ttfb_ms", 1500)),
        "transfer_kb": int(b.get("transfer_kb", 4096)),
    }


@allure.epic("质量属性")
@allure.feature("前端性能 Core Web Vitals")
class TestWebVitals:

    @allure.story("性能预算")
    @allure.title("PERF_{page_name} - 应满足性能预算")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.vitals
    @pytest.mark.p2
    def test_within_budget(self, page, goto, cfg, browser_engine,
                           page_name, path):
        if browser_engine != "chromium":
            pytest.skip("LCP / CLS 是 Chromium 专属 API，%s 不支持" % browser_engine)

        goto(path)
        m = page.evaluate(COLLECT_JS)
        budget = _budget(cfg)

        rows = [
            ("LCP  最大内容绘制", m["lcp"], budget["lcp_ms"], "ms"),
            ("CLS  累计布局偏移", m["cls"], budget["cls"], ""),
            ("FCP  首次内容绘制", m["fcp"], budget["fcp_ms"], "ms"),
            ("TTFB 首字节时间", m["ttfb"], budget["ttfb_ms"], "ms"),
            ("传输总量", m["transferKB"], budget["transfer_kb"], "KB"),
        ]
        allure.attach(
            "页面: %s\n\n%-22s %10s %10s\n%s\n%s\n\nDOMContentLoaded: %sms\nload: %sms"
            % (page_name, "指标", "实测", "预算", "-" * 44,
               "\n".join("%-22s %8s%-2s %8s%-2s  %s"
                         % (n, v, u, lim, u, "OK" if _ok(v, lim) else "超预算")
                         for n, v, lim, u in rows),
               m["domContentLoaded"], m["load"]),
            name="性能指标_%s" % page_name,
            attachment_type=allure.attachment_type.TEXT)

        sa = SoftAssert()
        for name, value, limit, unit in rows:
            if value is None:
                continue
            sa.true(value <= limit,
                    "%s 超出预算：实测 %s%s，预算 %s%s"
                    % (name.strip(), value, unit, limit, unit))
        sa.assert_all()

    @allure.story("阻塞渲染的资源")
    @allure.title("PERF_RENDER - 页面不应有过多阻塞渲染的资源")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.description(
        "head 里同步的 <script> 和非 media 限定的 <link rel=stylesheet> 会阻塞首屏渲染。\n"
        "这是 LCP 偏高最常见的根因，也是最容易改的一类问题\n"
        "（加 defer/async、把非关键 CSS 异步化）。"
    )
    @pytest.mark.vitals
    @pytest.mark.p2
    def test_render_blocking_resources(self, page, goto, site):
        goto(site.get("product_page") or site["pages"][-1][1])

        blocking = page.evaluate("""() => {
            const out = {scripts: [], styles: []};
            document.querySelectorAll('head script[src]').forEach(s => {
                if (!s.defer && !s.async && s.type !== 'module') {
                    out.scripts.push(s.src.slice(0, 110));
                }
            });
            document.querySelectorAll('head link[rel="stylesheet"]').forEach(l => {
                const m = l.getAttribute('media');
                if (!m || m === 'all' || m === 'screen') {
                    out.styles.push(l.href.slice(0, 110));
                }
            });
            return out;
        }""")

        total = len(blocking["scripts"]) + len(blocking["styles"])
        allure.attach(
            "阻塞渲染的脚本 %d 个:\n%s\n\n阻塞渲染的样式表 %d 个:\n%s"
            % (len(blocking["scripts"]),
               "\n".join("  " + s for s in blocking["scripts"]) or "  （无）",
               len(blocking["styles"]),
               "\n".join("  " + s for s in blocking["styles"]) or "  （无）"),
            name="阻塞渲染的资源",
            attachment_type=allure.attachment_type.TEXT)

        assert total <= 12, (
            "首页有 %d 个阻塞渲染的资源（脚本 %d + 样式 %d），会明显拖慢首屏。\n"
            "明细见报告附件。"
            % (total, len(blocking["scripts"]), len(blocking["styles"])))


def _ok(value, limit):
    return value is None or value <= limit
