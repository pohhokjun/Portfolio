# -*- coding: utf-8 -*-
"""
UI 测试专用 fixture

只放 UI 用例才需要的东西：注册账号、登录态。
接口客户端和页面对象在上一层 sites/automationexercise/conftest.py 里，这里能直接用。
"""

import pytest

from sites.automationexercise.api.user_api import UserApi
from common.faker_util import random_user
from common.logger import get_logger
from sites.automationexercise.pages.home_page import HomePage
from sites.automationexercise.pages.login_page import LoginPage

log = get_logger("ui.conftest")


@pytest.fixture
def registered_user(cfg):
    """
    ★ 接口造数据 + UI 验证 —— 行业最佳实践 ★

    为什么 UI 登录用例的账号要用接口注册，而不是用 UI 注册：

        UI 注册要填十几个字段、跨两个页面，慢且脆弱。
        如果注册页面改版，登录用例也跟着挂 —— 但登录功能其实没问题。
        这叫「用例的失败原因不聚焦」。

        用接口造数据：3 秒完成，不受 UI 改版影响，
        UI 用例只验证「登录」这一个被测点。

    面试话术：这体现测试金字塔思想 —— 能用接口做的绝不用 UI 做。
    """
    api = UserApi(cfg)
    user = random_user()
    api.create_account(user)
    log.info("UI用例前置：已通过接口注册账号 %s", user["email"])

    yield user

    try:
        api.delete_account(user["email"], user["password"])
        log.info("UI用例清理：已删除账号 %s", user["email"])
    except Exception as exc:
        log.warning("清理失败: %s", exc)


@pytest.fixture
def logged_in_page(page, cfg, registered_user):
    """已登录状态的首页。需要登录态的用例直接声明这个 fixture 即可。"""
    lp = LoginPage(page, cfg).open()
    lp.login(registered_user["email"], registered_user["password"])
    page.wait_for_timeout(1500)
    return HomePage(page, cfg)
