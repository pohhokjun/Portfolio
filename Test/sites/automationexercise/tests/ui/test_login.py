# -*- coding: utf-8 -*-
"""
登录功能 UI 测试

本文件演示：
    - POM 的实际用法（用例里看不到任何选择器）
    - 数据驱动的反向用例
    - 接口造数据 + UI 验证（测试金字塔思想）
    - 浏览器原生表单校验的处理
"""

import allure
import pytest

from sites.automationexercise import DATA

from common.assertions import assert_true, assert_in, SoftAssert
from common.data_reader import load_cases
from sites.automationexercise.pages.locators.login_loc import LoginLoc


@allure.epic("UI自动化")
@allure.feature("登录模块")
class TestLogin:

    @allure.story("正常登录")
    @allure.title("LOGIN_001 - 使用正确账号密码应登录成功")
    @allure.severity(allure.severity_level.BLOCKER)
    @allure.description(
        "用例设计方法：等价类划分-有效等价类\n"
        "前置条件：通过接口预先注册账号（不用UI注册，节省时间且更稳定）\n"
        "预期结果：登录成功，页面显示 Logged in as <用户名>"
    )
    @pytest.mark.ui
    @pytest.mark.smoke
    @pytest.mark.p0
    def test_login_success(self, login_page, registered_user):
        login_page.login(registered_user["email"], registered_user["password"])

        sa = SoftAssert()
        sa.true(login_page.is_logged_in(), "页面应显示已登录标识")
        sa.contains(login_page.logged_in_name(), registered_user["name"],
                    "显示的用户名应与注册用户一致")
        sa.assert_all()

        login_page.screenshot("登录成功")

    # -----------------------------------------------------------
    # 数据驱动的反向用例
    # -----------------------------------------------------------
    _cases, _ids = load_cases(DATA / "login_cases.yaml")

    @allure.story("异常登录")
    @allure.title("{case[title]}")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.ui
    @pytest.mark.negative
    @pytest.mark.p1
    @pytest.mark.parametrize("case", _cases, ids=_ids)
    def test_login_negative(self, login_page, case):
        """
        7 条异常场景，全部来自 yaml，覆盖：
            密码错误 / 账号不存在 / 邮箱格式非法 /
            必填为空 / 超长输入 / SQL注入字符
        """
        allure.dynamic.description(
            "用例ID: %s\n设计方法: %s\n输入邮箱: %r\n输入密码: %r"
            % (case["id"], case.get("method", ""),
               case["email"], case["password"])
        )

        login_page.login(case["email"], case["password"])

        # 核心断言：无论什么异常输入，都不能登录成功
        assert_true(not login_page.is_logged_in(),
                    "异常输入不应登录成功: %s" % case["title"])

        # 如果预期有错误提示，检查提示文案
        if case.get("expect_error"):
            error = login_page.get_login_error()
            assert_in(case["expect_error"][:20], error,
                      "应显示正确的错误提示")
        else:
            # 无提示文案的场景，验证浏览器原生校验或页面停留在登录页
            blocked = (login_page.is_html5_invalid(LoginLoc.LOGIN_EMAIL)
                       or login_page.is_html5_invalid(LoginLoc.LOGIN_PASSWORD)
                       or login_page.is_visible(LoginLoc.LOGIN_FORM_TITLE))
            assert_true(blocked, "应被表单校验拦截或停留在登录页")

    @allure.story("退出登录")
    @allure.title("LOGIN_009 - 登录后退出应回到登录页")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.ui
    @pytest.mark.p1
    def test_logout(self, logged_in_page):
        """使用 logged_in_page fixture，省去重复的登录步骤。"""
        assert_true(logged_in_page.is_logged_in(), "前置条件：应处于登录状态")

        logged_in_page.logout()

        assert_true(not logged_in_page.is_logged_in(), "退出后不应显示登录标识")
        assert_in("login", logged_in_page.url, "退出后应跳转到登录页")

    @allure.story("注册")
    @allure.title("SIGNUP_001 - 用已注册邮箱再次注册应被拒绝")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.ui
    @pytest.mark.negative
    @pytest.mark.p2
    def test_signup_duplicate_email(self, login_page, registered_user):
        login_page.signup(registered_user["name"], registered_user["email"])

        error = login_page.get_signup_error()
        assert_in("already exist", error.lower(),
                  "重复邮箱注册应提示邮箱已存在")
