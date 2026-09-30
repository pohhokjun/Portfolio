# -*- coding: utf-8 -*-
"""
视觉回归插件 —— UI 截图基线比对

【来源】原 17_测试/checkers/ui_check.py 的能力，改造成 pytest fixture。

★ 改造前后对比（面试可以直接讲这个演进）★

    改造前（自研平台）：
        需要在 cases/*.yaml 里定义一条 kind=ui 的用例，
        由自己写的 UIChecker 类执行，走自己的 runner 调度。

    改造后（pytest 插件）：
        任何用例里加一行 visual.check(page, "首页") 就能用。
        和 pytest 的 fixture、Allure 报告、失败截图全部打通。

    这就是「把自研能力接入标准生态」，
    比单纯自己造一套轮子更有价值。

用法：
    def test_homepage(self, page, visual):
        page.goto("https://example.com")
        visual.check(page, "首页")        # 首次建立基线，之后自动比对

命令行：
    pytest --update-baseline     用本次截图更新基线（确认改版无误后执行）
"""

from pathlib import Path

import allure
import pytest

from config.settings import get_config, SCREENSHOT_DIR, ROOT
from common.baseline import BaselineStore
from common.logger import get_logger

log = get_logger("visual")


class VisualChecker:
    """视觉回归检查器。通过 visual fixture 注入到用例里。"""

    def __init__(self, cfg, store, update_mode=False):
        self.cfg = cfg
        self.store = store
        self.update_mode = update_mode
        self.results = []

    def capture(self, page, name, full_page=True, freeze=True):
        """截图。freeze=True 会先把页面稳定下来，避免每次截图都不一样。"""
        # 先把窗口定成配置尺寸：浏览器平时是最大化（no_viewport），截图宽度会跟着屏幕走，
        # 1440 的基线拿 1920 的截图比，内容一样也判「变了」。页面每条用例新开，不用恢复。
        vp = self.cfg.get("viewport") or {}
        if vp.get("width") and vp.get("height"):
            page.set_viewport_size({"width": int(vp["width"]), "height": int(vp["height"])})
        if freeze:
            self._stabilize(page)
        path = SCREENSHOT_DIR / ("visual_%s.png" % name)
        page.screenshot(path=str(path), full_page=full_page)
        return str(path)

    def check(self, page, name, case_id=None, threshold=None, full_page=True):
        """
        截图并与基线比对。

        返回比对结果字典；差异超阈值时直接断言失败。

        参数：
            name       基线名称，同一页面每次要用同样的名字
            threshold  本次的差异阈值，不传则用配置里的默认值
        """
        case_id = case_id or "visual"
        current = self.capture(page, name, full_page=full_page)

        allure.attach.file(current, name="当前截图_%s" % name,
                           attachment_type=allure.attachment_type.PNG)

        # 更新模式：直接覆盖基线，不做比对
        if self.update_mode:
            self.store.update_image(case_id, name, current)
            log.info("已更新基线: %s/%s", case_id, name)
            return {"status": "updated"}

        out_dir = ROOT / "reports" / "screenshots"
        res = self.store.compare_image(case_id, name, current, out_dir=out_dir)
        self.results.append({"name": name, **res})

        status = res.get("status")

        if status == "created":
            allure.attach("首次运行，已建立基线。下次执行会开始比对。",
                          name="视觉回归_%s" % name,
                          attachment_type=allure.attachment_type.TEXT)
            log.info("已建立基线: %s/%s", case_id, name)
            return res

        if status == "skip":
            pytest.skip("视觉比对跳过：%s" % res.get("message"))

        if status == "missing":
            pytest.skip("缺少基线，请先运行一次以建立基线")

        if status == "changed":
            # 把基线图和差异图都贴进报告，方便判断是不是预期内的改版
            if res.get("baseline_image"):
                allure.attach.file(res["baseline_image"],
                                   name="基线截图_%s" % name,
                                   attachment_type=allure.attachment_type.PNG)
            if res.get("diff_image") and Path(res["diff_image"]).exists():
                allure.attach.file(res["diff_image"],
                                   name="差异标记_%s" % name,
                                   attachment_type=allure.attachment_type.PNG)
            pytest.fail(
                "界面发生非预期变化 [%s]\n%s\n"
                "如果这是正常的改版，执行 pytest --update-baseline 更新基线"
                % (name, res.get("message")))

        allure.attach("界面与基线一致（差异 %.4f%%）"
                      % ((res.get("changed_ratio") or 0) * 100),
                      name="视觉回归_%s" % name,
                      attachment_type=allure.attachment_type.TEXT)
        return res

    def check_schema(self, payload, name, case_id=None):
        """
        接口响应结构回归。

        值可以变，结构不能随便变。
        字段消失、类型改变都会被检出 —— 这是接口契约的守护。
        """
        from common.baseline import schema_of
        case_id = case_id or "schema"
        res = self.store.compare_data(case_id, name, schema_of(payload))

        if res["status"] == "changed":
            detail = "\n".join(
                "  %s : %s -> %s" % (c["path"], c["baseline"], c["current"])
                for c in res["changes"][:20])
            allure.attach(detail, name="接口结构变化_%s" % name,
                          attachment_type=allure.attachment_type.TEXT)
            pytest.fail("接口响应结构发生变化 [%s]:\n%s\n"
                        "如果是正常迭代，执行 pytest --update-baseline 更新"
                        % (name, detail))
        return res

    # 广告 / 第三方嵌入内容的容器。这些东西每次刷新都不一样，
    # 留着比对必然误报，截图前统一按固定尺寸的灰块处理。
    _AD_SELECTORS = (
        'iframe[id^="google_ads"]', 'iframe[id^="aswift"]', 'iframe[name^="aswift"]',
        'ins.adsbygoogle', '.adsbygoogle', '#fixedban', '.fixedban',
        '[id^="div-gpt-ad"]', 'iframe[src*="googlesyndication"]',
        'iframe[src*="doubleclick"]', 'iframe[src*="adservice"]',
    )

    @classmethod
    def _stabilize(cls, page):
        """
        截图前把页面「按住」。

        视觉回归 90% 的误报都出在这一步没做够。四类不稳定源：
            1. CSS 动画 / 过渡 / 输入框光标  -> 全局禁用
            2. 轮播图自动切换                -> 强制切回第一屏
            3. 广告和第三方 iframe           -> 内容每次都变，先藏起来
            4. 懒加载图片没加载完            -> 强制 loading=eager 并等图片就绪

        第 3 条是这个站点登录页的实际问题：挂着 Google 广告，
        广告一换基线就差 2.6%，超过 2% 阈值，用例天天红。
        这种失败没有任何信息量，只会让人不再相信报告。

        ★ 第 2 条是这里最值得讲的一个坑 ★
            首页的轮播图是 JS 定时切的（Bootstrap carousel 那一套），
            不是 CSS 动画。禁用 animation/transition 对它一点用没有 ——
            定时器照转，截到第几屏纯看运气。
            实测同一分钟内连拍差异只有 0.2%，隔二十分钟再拍就是 2.8%，
            差异图上能看到两屏的文字叠在一起。
            结论：视觉回归里「冻结动画」远远不够，
            凡是靠 JS 定时改 DOM 的东西，都得显式掰回固定状态。
        """
        try:
            page.evaluate(
                """(adSelectors) => {
                    const style = document.createElement('style');
                    style.textContent =
                        '*,*::before,*::after{'
                        + 'animation:none!important;'
                        + 'transition:none!important;'
                        + 'caret-color:transparent!important}'
                        // 藏滚动条：有头 Chrome 会画 15px 滚动条、整页左移 7px，
                        // 无头/叠加滚动条又不画 —— 同一页面基线差 2.2%，纯属环境噪声
                        + 'html{scrollbar-width:none!important}'
                        + '::-webkit-scrollbar{display:none!important}';
                    document.head.appendChild(style);

                    // 广告位不隐藏、只涂灰：保持占位高度，
                    // 否则整页高度会变，反而触发「尺寸不一致」。
                    document.querySelectorAll(adSelectors.join(',')).forEach(el => {
                        el.style.setProperty('visibility', 'hidden', 'important');
                    });

                    // 懒加载图片：强制立刻加载，避免截图时还是空白占位
                    document.querySelectorAll('img[loading="lazy"]').forEach(img => {
                        img.loading = 'eager';
                    });

                    // 轮播图掰回第一屏。
                    // 先停掉 Bootstrap 自己的定时器（有 jQuery 才有这个 API），
                    // 再直接改 DOM —— 不管用的是哪套轮播库，
                    // 「第一个子项带 active」这个约定基本是通用的。
                    try {
                        if (window.jQuery) { window.jQuery('.carousel').carousel('pause'); }
                    } catch (e) {}
                    document.querySelectorAll(
                        '.carousel, .slider, [data-ride="carousel"]'
                    ).forEach(box => {
                        const items = box.querySelectorAll(
                            ':scope .carousel-item, :scope .item');
                        items.forEach((it, i) => it.classList.toggle('active', i === 0));
                        box.querySelectorAll(
                            ':scope .carousel-indicators li'
                        ).forEach((li, i) => li.classList.toggle('active', i === 0));
                    });

                    window.scrollTo(0, 0);
                }""",
                list(cls._AD_SELECTORS))
            # 等图片解码完成，再等一帧让样式生效
            page.evaluate("""() => Promise.all(
                Array.from(document.images)
                     .filter(i => !i.complete)
                     .map(i => new Promise(r => { i.onload = i.onerror = r; }))
            )""")
            page.wait_for_timeout(300)
        except Exception:
            pass


# ===============================================================
# pytest 集成
# ===============================================================
def pytest_addoption(parser):
    parser.addoption("--update-baseline", action="store_true", default=False,
                     help="用本次截图更新视觉基线（确认改版无误后使用）")


@pytest.fixture(scope="session")
def baseline_store(cfg):
    return BaselineStore(cfg)


@pytest.fixture
def visual(request, cfg, baseline_store):
    """视觉回归检查器。在用例里声明 visual 参数即可使用。"""
    update = request.config.getoption("--update-baseline")
    checker = VisualChecker(cfg, baseline_store, update_mode=update)
    yield checker
