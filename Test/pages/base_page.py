# -*- coding: utf-8 -*-
"""
页面基类 —— POM 的核心

设计说明（面试必讲）：
    所有页面类都继承它，拿到统一的：
        点击、输入、等待、截图、断言辅助
    每个动作都自动记录到 Allure，失败自动截图。

    好处：
        1. 用例层不用直接碰 Playwright API，换成 Selenium 只改这一个文件
        2. 所有等待策略统一，避免有人写 sleep(3) 有人写显式等待
        3. 报告里能看到「点击了什么」「输入了什么」

【第二期融合点】
    17_测试/web/actions.py 的能力可以合并到这里；
    截图基线比对（core/baseline.py）可作为 assert_visual() 方法加入。
"""

import allure
from playwright.sync_api import Page, TimeoutError as PWTimeout

from config.settings import get_config, SCREENSHOT_DIR
from common.logger import get_logger

log = get_logger("page")


class BasePage:
    """所有页面对象的父类。"""

    # 子类可以覆盖，用于 open() 直接打开自己的路径
    PATH = "/"

    def __init__(self, page: Page, cfg=None):
        self.page = page
        self.cfg = cfg or get_config()
        self.page.set_default_timeout(self.cfg.timeout)

    # -----------------------------------------------------------
    # 导航
    # -----------------------------------------------------------
    # 被测站点限流时会返回一个「5秒后自动刷新」的等待页
    _READY_MARKER = 'a[href="/products"]'      # 真实页面都有的顶部导航
    _NAV_RETRY = 3

    def open(self, path=None):
        """
        打开页面。

        ★ 实战踩坑（面试可讲）★
            被测站点有反爬限流，请求过密时会先返回一个
            「5秒后自动刷新」的 HTML 等待页，页面上没有任何业务元素。
            如果直接 goto 后就找元素，就会随机报「元素找不到」，
            表现为用例时好时坏（Flaky Test）。

            处理方式不是加 sleep，而是：
                1. 定义「页面就绪」的判据（顶部导航是否出现）
                2. 没就绪就退避重试，间隔递增
            这样既稳定，又不会无谓地拖慢每条用例。
        """
        target = path if path is not None else self.PATH
        url = target if target.startswith("http") else self.cfg.base_url + target

        with allure.step("打开页面: %s" % url):
            for attempt in range(1, self._NAV_RETRY + 1):
                try:
                    self.page.goto(url, timeout=self.cfg.nav_timeout,
                                   wait_until="domcontentloaded")
                except Exception as exc:
                    # 限流等待页自带 5 秒后 reload 的脚本，
                    # 它自己跳转会打断我们的 goto，抛 ERR_ABORTED。
                    # 这不是真的失败，忽略后继续判断页面是否就绪。
                    if "ERR_ABORTED" not in str(exc):
                        raise
                    log.debug("导航被页面自身刷新打断，继续等待: %s", url)

                if self.is_page_ready():
                    break

                log.warning("页面未就绪(疑似限流等待页)，等待自动刷新 (%d/%d): %s",
                            attempt, self._NAV_RETRY, url)
                self.page.wait_for_timeout(6000)
                if self.is_page_ready():
                    break
            self.dismiss_ads()
        return self

    def is_page_ready(self, timeout=8000):
        """页面是否真正加载出业务内容（而非限流等待页）。"""
        try:
            self.page.locator(self._READY_MARKER).first.wait_for(
                state="attached", timeout=timeout)
            return True
        except Exception:
            return False

    def reload(self):
        self.page.reload(wait_until="domcontentloaded")
        return self

    @property
    def url(self):
        return self.page.url

    @property
    def title(self):
        return self.page.title()

    # -----------------------------------------------------------
    # 基础操作
    # -----------------------------------------------------------
    def click(self, selector, desc=""):
        with allure.step("点击: %s" % (desc or selector)):
            log.debug("click %s", selector)
            self.dismiss_ads()
            loc = self.page.locator(selector).first
            # 滚到视口正中，而不是「刚好露出来」——
            # 最小滚动会让元素停在边缘，正好被固定页头/底部广告条盖住。
            loc.evaluate("el => el.scrollIntoView({block: 'center', inline: 'center'})")
            loc.click()
        return self

    def fill(self, selector, value, desc=""):
        with allure.step("输入 [%s]: %s" % (desc or selector, value)):
            log.debug("fill %s = %s", selector, value)
            loc = self.page.locator(selector).first
            loc.wait_for(state="visible")
            loc.fill(str(value))
        return self

    def get_text(self, selector, default=""):
        try:
            return (self.page.locator(selector).first.inner_text() or "").strip()
        except Exception:
            return default

    def get_all_texts(self, selector):
        try:
            return [t.strip() for t in self.page.locator(selector).all_inner_texts()]
        except Exception:
            return []

    def count(self, selector):
        try:
            return self.page.locator(selector).count()
        except Exception:
            return 0

    def page_text(self):
        try:
            return self.page.inner_text("body")
        except Exception:
            return ""

    # -----------------------------------------------------------
    # 等待与判断
    # -----------------------------------------------------------
    def is_visible(self, selector, timeout=5000):
        """元素是否可见。不抛异常，返回布尔值，用于断言。"""
        try:
            self.page.locator(selector).first.wait_for(state="visible",
                                                       timeout=timeout)
            return True
        except PWTimeout:
            return False
        except Exception:
            return False

    def wait_for(self, selector, timeout=None, state="visible"):
        self.page.locator(selector).first.wait_for(
            state=state, timeout=timeout or self.cfg.timeout)
        return self

    def wait_url_contains(self, fragment, timeout=None):
        self.page.wait_for_url("**%s**" % fragment,
                               timeout=timeout or self.cfg.nav_timeout)
        return self

    # -----------------------------------------------------------
    # 广告处理
    # -----------------------------------------------------------
    # 各站点的关闭按钮不一样，站点的页面基类里覆盖这个列表
    AD_CLOSE = ()

    def dismiss_ads(self):
        """
        被测站点挂了广告，偶尔会盖住按钮导致点击失败。
        这是真实项目里天天遇到的问题，处理方式就是主动关闭 / 忽略。

        面试话术：自动化的稳定性问题，80% 来自弹窗、广告、动画和网络抖动。
        """
        try:
            for sel in self.AD_CLOSE:
                loc = self.page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible(timeout=500):
                    loc.first.click(timeout=1000)
                    log.debug("已关闭广告: %s", sel)
        except Exception:
            pass
        return self

    # -----------------------------------------------------------
    # 截图
    # -----------------------------------------------------------
    def screenshot(self, name="screenshot", full_page=True):
        """截图并自动挂到 Allure 报告。"""
        try:
            path = SCREENSHOT_DIR / ("%s.png" % name)
            self.page.screenshot(path=str(path), full_page=full_page)
            allure.attach.file(str(path), name=name,
                               attachment_type=allure.attachment_type.PNG)
            return str(path)
        except Exception as exc:
            log.warning("截图失败: %s", exc)
            return None
