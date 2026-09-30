# -*- coding: utf-8 -*-
"""
登录 / 注册页

注意这里的方法命名：
    login()          执行动作，不做断言
    get_error_msg()  提供数据，让用例去断言

    页面对象只负责「怎么操作页面」，不负责「结果对不对」。
    断言必须写在用例里 —— 这是 POM 的铁律，面试常考。
"""

import allure

from sites.automationexercise.pages.site_page import SitePage
from sites.automationexercise.pages.locators.login_loc import LoginLoc


class LoginPage(SitePage):
    PATH = "/login"

    @allure.step("验证登录页已加载")
    def is_loaded(self):
        return self.is_visible(LoginLoc.LOGIN_FORM_TITLE)

    @allure.step("执行登录: {email}")
    def login(self, email, password):
        self.fill(LoginLoc.LOGIN_EMAIL, email, "邮箱")
        self.fill(LoginLoc.LOGIN_PASSWORD, password, "密码")
        self.click(LoginLoc.LOGIN_BUTTON, "登录按钮")
        return self

    @allure.step("填写注册信息: {name} / {email}")
    def signup(self, name, email):
        self.fill(LoginLoc.SIGNUP_NAME, name, "用户名")
        self.fill(LoginLoc.SIGNUP_EMAIL, email, "注册邮箱")
        self.click(LoginLoc.SIGNUP_BUTTON, "注册按钮")
        return self

    def get_login_error(self):
        """登录失败提示。没有提示时返回空串。"""
        if self.is_visible(LoginLoc.LOGIN_ERROR, timeout=4000):
            return self.get_text(LoginLoc.LOGIN_ERROR)
        return ""

    def get_signup_error(self):
        if self.is_visible(LoginLoc.SIGNUP_ERROR, timeout=4000):
            return self.get_text(LoginLoc.SIGNUP_ERROR)
        return ""

    def is_html5_invalid(self, selector):
        """
        检查浏览器原生表单校验是否拦截。

        为什么需要：邮箱格式错误时，浏览器自己就拦下了，
        页面不会有任何提示文案，只能通过 JS 读取校验状态。
        这是 UI 自动化的一个常见坑点。
        """
        try:
            return self.page.locator(selector).first.evaluate(
                "el => el.willValidate ? !el.checkValidity() : false")
        except Exception:
            return False
