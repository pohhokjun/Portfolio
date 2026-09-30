# -*- coding: utf-8 -*-
"""
购物车流程测试 —— 场景法用例设计

场景法（业务流程法）是什么：
    不针对单个功能点，而是模拟用户完成一个完整业务目标的路径。
    比如「浏览商品 -> 加入购物车 -> 查看购物车 -> 核对金额 -> 删除」。

为什么重要：
    单个功能都正常，串起来可能出问题。
    比如加购成功、购物车页面也能打开，但金额算错了。
    面试问「你除了等价类边界值还会什么」，答场景法，并举这个例子。
"""

import allure
import pytest

from common.assertions import assert_true, assert_equal, SoftAssert


@allure.epic("UI自动化")
@allure.feature("购物车模块")
class TestCartFlow:

    @allure.story("加入购物车")
    @allure.title("CART_001 - 添加单个商品到购物车")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.ui
    @pytest.mark.smoke
    @pytest.mark.p0
    def test_add_single_product(self, products_page):
        products_page.add_to_cart(1)
        cart = products_page.view_cart()

        sa = SoftAssert()
        sa.true(cart.is_loaded(), "购物车页应加载")
        sa.equal(cart.item_count(), 1, "购物车应有1件商品")
        sa.assert_all()

        cart.screenshot("购物车-单件商品")
        cart.clear()      # 数据清理

    @allure.story("加入购物车")
    @allure.title("CART_002 - 添加多个商品到购物车")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.ui
    @pytest.mark.p1
    def test_add_multiple_products(self, products_page):
        for i in (1, 2, 3):
            products_page.add_to_cart(i)
            products_page.continue_shopping()

        cart = products_page.go_cart()

        assert_equal(cart.item_count(), 3, "购物车应有3件商品")
        cart.clear()

    @allure.story("金额计算")
    @allure.title("CART_003 - 购物车金额计算应正确（单价×数量=小计）")
    @allure.severity(allure.severity_level.BLOCKER)
    @allure.description(
        "这是一条「业务规则断言」用例。\n"
        "只验证元素存在是不够的，必须验证业务逻辑正确性。\n"
        "金额算错是电商系统最严重的缺陷类型之一。"
    )
    @pytest.mark.ui
    @pytest.mark.p0
    def test_cart_amount_calculation(self, products_page):
        for i in (1, 2):
            products_page.add_to_cart(i)
            products_page.continue_shopping()

        cart = products_page.go_cart()
        items = cart.get_items()

        assert_true(len(items) > 0, "前置条件：购物车不能为空")

        sa = SoftAssert()
        for item in items:
            expected = item["price"] * item["quantity"]
            sa.equal(item["total"], expected,
                     "商品[%s] 单价%d × 数量%d 应等于小计"
                     % (item["name"][:20], item["price"], item["quantity"]))

        allure.attach(
            "\n".join("%-30s 单价:%-6d 数量:%-3d 小计:%d"
                      % (i["name"][:30], i["price"], i["quantity"], i["total"])
                      for i in items),
            name="购物车明细",
            attachment_type=allure.attachment_type.TEXT)

        sa.assert_all()
        cart.clear()

    @allure.story("删除商品")
    @allure.title("CART_004 - 从购物车删除商品")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.ui
    @pytest.mark.p1
    def test_remove_from_cart(self, products_page):
        products_page.add_to_cart(1)
        products_page.continue_shopping()
        products_page.add_to_cart(2)

        cart = products_page.view_cart()
        before = cart.item_count()
        assert_equal(before, 2, "前置条件：应有2件商品")

        cart.remove_item(0)

        assert_equal(cart.item_count(), before - 1, "删除后应少1件")
        cart.clear()

    @allure.story("端到端流程")
    @allure.title("E2E - 登录用户完整购物流程")
    @allure.severity(allure.severity_level.BLOCKER)
    @allure.description(
        "场景法用例：模拟真实用户的完整路径\n"
        "登录 -> 浏览商品 -> 加购 -> 查看购物车 -> 核对 -> 清空"
    )
    @pytest.mark.ui
    @pytest.mark.p0
    def test_e2e_shopping_flow(self, logged_in_page, cfg):
        from sites.automationexercise.pages.products_page import ProductsPage
        from sites.automationexercise.pages.cart_page import CartPage

        sa = SoftAssert()

        with allure.step("步骤1：确认登录状态"):
            sa.true(logged_in_page.is_logged_in(), "应处于登录状态")

        with allure.step("步骤2：进入商品列表"):
            products = ProductsPage(logged_in_page.page, cfg).open()
            sa.true(products.product_count() > 0, "商品列表应有商品")

        with allure.step("步骤3：加入购物车"):
            products.add_to_cart(1)
            products.continue_shopping()

        with allure.step("步骤4：查看购物车"):
            cart = CartPage(logged_in_page.page, cfg).open()
            sa.equal(cart.item_count(), 1, "购物车应有1件商品")

        with allure.step("步骤5：验证登录状态未丢失"):
            sa.true(cart.is_logged_in(), "购物流程中登录状态应保持")

        with allure.step("步骤6：清空购物车"):
            cart.clear()
            sa.true(cart.item_count() == 0 or cart.is_empty(), "购物车应已清空")

        sa.assert_all()
