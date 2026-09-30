# -*- coding: utf-8 -*-
"""
用户相关接口

对应 automationexercise 的 API 7-14。
覆盖注册、登录校验、更新、删除、查询，是一条完整的数据生命周期，
非常适合演示「测试数据的创建与清理」。
"""

import allure

from api.base_api import BaseApi


class UserApi(BaseApi):

    @allure.step("接口：校验登录")
    def verify_login(self, email=None, password=None):
        payload = {}
        if email is not None:
            payload["email"] = email
        if password is not None:
            payload["password"] = password
        return self.post("/verifyLogin", data=payload)

    @allure.step("接口：用 DELETE 请求登录校验（预期 405）")
    def delete_verify_login(self):
        return self.delete("/verifyLogin")

    @allure.step("接口：注册新账号")
    def create_account(self, user: dict):
        return self.post("/createAccount", data=user)

    @allure.step("接口：删除账号")
    def delete_account(self, email, password):
        return self.delete("/deleteAccount",
                           data={"email": email, "password": password})

    @allure.step("接口：更新账号信息")
    def update_account(self, user: dict):
        return self.put("/updateAccount", data=user)

    @allure.step("接口：按邮箱查询用户详情")
    def get_user_by_email(self, email):
        return self.get("/getUserDetailByEmail", params={"email": email})
