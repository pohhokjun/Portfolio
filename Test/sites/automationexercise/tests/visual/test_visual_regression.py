# -*- coding: utf-8 -*-
"""
视觉回归测试 —— UI 截图基线比对

★ pytest 生态里没有的能力，本项目自研 ★

工作原理：
    第一次运行  → 截图存为「基线」，用例通过
    之后运行    → 新截图和基线逐像素比对，差异超阈值就失败
    确认是正常改版 → pytest --update-baseline 更新基线

解决的问题：
    普通断言只能验证「你想到要检查的东西」。
    但改版时很多变化你根本想不到要断言 ——
    按钮颜色变了、间距乱了、某个模块整块消失了。
    视觉回归反过来做：和上次不一样就告警。

常见坑（面试可讲）：
    1. 页面有动画 → 每次截图都不同 → 用 freeze 冻结动画
    2. 有时间戳/轮播图 → 必然变化 → 用 ignore_boxes 屏蔽
    3. 不同分辨率截图不同 → 固定 viewport
    4. 字体渲染差异 → 设 pixel_threshold 容忍噪声

    这四点都在框架里处理了。

首次运行会全部「建立基线」并通过，第二次开始才真正比对。
"""

import allure
import pytest

from sites.automationexercise.pages.home_page import HomePage
from sites.automationexercise.pages.login_page import LoginPage
from sites.automationexercise.pages.products_page import ProductsPage


@allure.epic("视觉回归")
@allure.feature("页面外观一致性")
class TestVisualRegression:

    @allure.story("首页")
    @allure.title("VISUAL_001 - 首页外观与基线一致")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.visual
    @pytest.mark.p2
    def test_home_page_visual(self, page, cfg, visual):
        HomePage(page, cfg).open()
        page.wait_for_timeout(1500)      # 等图片加载完
        visual.check(page, "home", case_id="visual_home", full_page=False)

    @allure.story("登录页")
    @allure.title("VISUAL_002 - 登录页外观与基线一致")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.visual
    @pytest.mark.p2
    def test_login_page_visual(self, page, cfg, visual):
        LoginPage(page, cfg).open()
        page.wait_for_timeout(1000)
        visual.check(page, "login", case_id="visual_login", full_page=False)

    @allure.story("商品页")
    @allure.title("VISUAL_003 - 商品列表页外观与基线一致")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.visual
    @pytest.mark.p2
    def test_products_page_visual(self, page, cfg, visual):
        ProductsPage(page, cfg).open()
        page.wait_for_timeout(1500)
        visual.check(page, "products", case_id="visual_products",
                     full_page=False)


@allure.epic("视觉回归")
@allure.feature("接口结构一致性")
class TestSchemaRegression:
    """
    接口响应结构回归。

    值可以变（商品价格会调整），结构不能随便变（字段不能消失）。
    这是接口契约的守护 —— 前端最怕后端偷偷改字段。
    """

    @allure.story("商品接口")
    @allure.title("SCHEMA_001 - 商品列表接口响应结构未变化")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.visual
    @pytest.mark.api
    @pytest.mark.p1
    def test_products_schema(self, product_api, visual):
        resp = product_api.get_all_products()
        body = product_api.json_of(resp)

        # 只取第一个商品做结构基线，避免数据量影响
        sample = {
            "responseCode": body.get("responseCode"),
            "products": (body.get("products") or [])[:1],
        }
        visual.check_schema(sample, "products_list", case_id="schema_api")

    @allure.story("品牌接口")
    @allure.title("SCHEMA_002 - 品牌列表接口响应结构未变化")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.visual
    @pytest.mark.api
    @pytest.mark.p2
    def test_brands_schema(self, product_api, visual):
        resp = product_api.get_all_brands()
        body = product_api.json_of(resp)
        sample = {
            "responseCode": body.get("responseCode"),
            "brands": (body.get("brands") or [])[:1],
        }
        visual.check_schema(sample, "brands_list", case_id="schema_api")
