# -*- coding: utf-8 -*-
"""首页"""

import allure

from sites.automationexercise.pages.site_page import SitePage
from sites.automationexercise.pages.locators.common_loc import CommonLoc


class HomePage(SitePage):
    PATH = "/"

    SLIDER = '#slider'
    FEATURES = '.features_items'

    @allure.step("验证首页已加载")
    def is_loaded(self):
        return self.is_visible(self.SLIDER) or self.is_visible(self.FEATURES)

    @allure.step("从首页进入商品列表")
    def go_products(self):
        from sites.automationexercise.pages.products_page import ProductsPage
        self.click(CommonLoc.NAV_PRODUCTS, "商品菜单")
        return ProductsPage(self.page, self.cfg)

    @allure.step("从首页进入登录页")
    def go_login(self):
        from sites.automationexercise.pages.login_page import LoginPage
        self.click(CommonLoc.NAV_LOGIN, "登录菜单")
        return LoginPage(self.page, self.cfg)

    @allure.step("从首页进入购物车")
    def go_cart(self):
        from sites.automationexercise.pages.cart_page import CartPage
        self.click(CommonLoc.NAV_CART, "购物车菜单")
        return CartPage(self.page, self.cfg)
