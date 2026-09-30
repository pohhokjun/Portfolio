# -*- coding: utf-8 -*-
"""页面对象里「不需要浏览器」的那部分逻辑的自测。

页面对象大部分方法要真浏览器，测不了也不该在这里测。
但金额解析、定位器拼接这些是纯逻辑，恰恰又是最容易出 bug 的地方 ——
购物车金额算错是电商系统最严重的缺陷类型之一，
而解析函数把 "Rs. 1,200" 读成 1 的话，用例还会显示通过。
"""

import pytest

from sites.automationexercise.pages.cart_page import CartPage
from sites.automationexercise.pages.locators.products_loc import ProductsLoc


class TestPriceParsing:

    @pytest.mark.parametrize("text,expected", [
        ("Rs. 500", 500),
        ("Rs.500", 500),
        ("Rs. 1,200", 1200),          # 千分位逗号
        ("Rs. 1,234,567", 1234567),
        ("  Rs. 500  ", 500),
        ("500", 500),
        ("Rs. 0", 0),
    ])
    def test_从价格文案里取出数字(self, text, expected):
        assert CartPage._to_number(text) == expected

    @pytest.mark.parametrize("text", ["", "免费", None, "Rs. --"])
    def test_取不到数字时返回0而不是崩(self, text):
        assert CartPage._to_number(text) == 0

    def test_数字类型直接传进来也能处理(self):
        assert CartPage._to_number(500) == 500

    def test_只取第一段数字(self):
        assert CartPage._to_number("Rs. 500 x 2") == 500


class TestProductsLocator:

    def test_加购按钮用的是选一组再取第几个(self):
        # 曾经这里写的是 :nth-child(%d)，永远只能拿到第 1 个商品。
        # 原因：:nth-child 数的是「在父节点里排第几」，
        # 而每个商品卡片都是自己父节点唯一的孩子。
        # 这条用例把「不许再用 nth-child」这个结论钉住。
        assert not hasattr(ProductsLoc, "ADD_TO_CART_NTH")
        assert "nth-child" not in ProductsLoc.ADD_TO_CART_ALL
        assert "%" not in ProductsLoc.ADD_TO_CART_ALL

    def test_加购按钮限定在商品列表区域内(self):
        # 不限定的话会选到页脚「推荐商品」轮播里的按钮，序号全乱
        assert ProductsLoc.ADD_TO_CART_ALL.startswith(".features_items")


class TestPageObjectContract:
    """POM 的铁律：页面之间跳转必须返回目标页对象。"""

    def test_商品页有明确的跳购物车方法(self):
        from sites.automationexercise.pages.products_page import ProductsPage
        assert callable(ProductsPage.go_cart)

    def test_open返回自己所以不能拿来做跨页跳转(self):
        # 这就是之前 test_cart_flow 里那个 bug：
        # products_page.open("/view_cart") 拿到的还是 ProductsPage，
        # 上面根本没有 item_count()，一调就 AttributeError
        from sites.automationexercise.pages.products_page import ProductsPage
        assert not hasattr(ProductsPage, "item_count")
        assert hasattr(CartPage, "item_count")

    @pytest.mark.parametrize("cls,path", [
        ("sites.automationexercise.pages.home_page:HomePage", "/"),
        ("sites.automationexercise.pages.login_page:LoginPage", "/login"),
        ("sites.automationexercise.pages.products_page:ProductsPage", "/products"),
        ("sites.automationexercise.pages.cart_page:CartPage", "/view_cart"),
    ])
    def test_每个页面对象都声明了自己的路径(self, cls, path):
        import importlib
        mod, name = cls.split(":")
        assert getattr(importlib.import_module(mod), name).PATH == path

    def test_页面对象不做断言(self):
        # 断言属于用例层。页面对象里出现 assert 就是分层坏了
        import inspect
        from pages import base_page
        from sites.automationexercise.pages import (cart_page, home_page, login_page,
                                                   products_page, site_page)
        for mod in (base_page, site_page, cart_page, home_page, login_page, products_page):
            src = inspect.getsource(mod)
            code = "\n".join(l for l in src.splitlines()
                             if not l.strip().startswith("#"))
            assert "\n    assert " not in code, "%s 里不该有断言" % mod.__name__
