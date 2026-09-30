# -*- coding: utf-8 -*-
"""
商品相关接口

对应 automationexercise 的 API 1-6。
每个方法只做一件事：发请求、返回 response。
断言不写在这里 —— 断言属于用例层，这是分层的原则。
"""

import allure

from api.base_api import BaseApi


class ProductApi(BaseApi):

    @allure.step("接口：获取全部商品列表")
    def get_all_products(self):
        return self.get("/productsList")

    @allure.step("接口：用 POST 请求商品列表（预期 405）")
    def post_products_list(self):
        return self.post("/productsList")

    @allure.step("接口：获取全部品牌列表")
    def get_all_brands(self):
        return self.get("/brandsList")

    @allure.step("接口：用 PUT 请求品牌列表（预期 405）")
    def put_brands_list(self):
        return self.put("/brandsList")

    @allure.step("接口：搜索商品 keyword={keyword}")
    def search_product(self, keyword):
        return self.post("/searchProduct", data={"search_product": keyword})

    @allure.step("接口：搜索商品但不传参数（预期 400）")
    def search_product_without_param(self):
        return self.post("/searchProduct")
