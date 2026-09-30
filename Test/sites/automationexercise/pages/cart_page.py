# -*- coding: utf-8 -*-
"""购物车页"""

import re

import allure

from sites.automationexercise.pages.site_page import SitePage
from sites.automationexercise.pages.locators.cart_loc import CartLoc


class CartPage(SitePage):
    PATH = "/view_cart"

    @allure.step("验证购物车页已加载")
    def is_loaded(self):
        return self.is_visible(CartLoc.CART_TABLE, timeout=8000) \
            or self.is_visible(CartLoc.EMPTY_CART, timeout=3000)

    def is_empty(self):
        return self.is_visible(CartLoc.EMPTY_CART, timeout=3000)

    def item_count(self):
        return self.count(CartLoc.CART_ROWS)

    def item_names(self):
        return self.get_all_texts(CartLoc.PRODUCT_NAME)

    def get_items(self):
        """
        返回购物车全部商品的结构化数据。

        用于金额校验：单价 x 数量 == 小计
        这是典型的「业务规则断言」，比只判断元素存在有价值得多。
        """
        items = []
        rows = self.page.locator(CartLoc.CART_ROWS)
        for i in range(rows.count()):
            row = rows.nth(i)
            try:
                name = row.locator(CartLoc.PRODUCT_NAME).inner_text().strip()
                price = self._to_number(row.locator(CartLoc.PRODUCT_PRICE).inner_text())
                qty = int(row.locator(CartLoc.PRODUCT_QUANTITY).inner_text().strip())
                total = self._to_number(row.locator(CartLoc.PRODUCT_TOTAL).inner_text())
                items.append({"name": name, "price": price,
                              "quantity": qty, "total": total})
            except Exception:
                continue
        return items

    @allure.step("删除购物车第 {index} 项")
    def remove_item(self, index=0):
        self.page.locator(CartLoc.DELETE_BUTTON).nth(index).click()
        self.page.wait_for_timeout(1200)
        return self

    def clear(self):
        """清空购物车 —— 用例执行后的数据清理。"""
        while self.count(CartLoc.DELETE_BUTTON) > 0:
            self.remove_item(0)
        return self

    @staticmethod
    def _to_number(text):
        """'Rs. 500' -> 500"""
        m = re.search(r"(\d[\d,]*)", str(text).replace(" ", ""))
        return int(m.group(1).replace(",", "")) if m else 0
