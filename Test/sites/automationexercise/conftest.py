# -*- coding: utf-8 -*-
"""
AutomationExercise 这个站的 fixture —— 本站所有用例目录共享

fixture 的层级设计（面试可讲）：
    conftest.py                              最外层：浏览器、失败截图钩子
    sites/automationexercise/conftest.py     本层：本站配置、接口客户端、页面对象、测试数据  ← 当前文件
    sites/automationexercise/tests/ui/conftest.py 更内层：只有 UI 用例需要的登录态

    放在这一层的原因：
        安全测试既要调接口又要用页面对象，
        性能测试要用接口客户端，
        所以这些通用能力必须放在共同的父目录，子目录才能都看到。

    这就是 conftest 层级继承的实际价值。
"""

import pytest

from plugins.site_plugin import probe, site_cfg
from sites.automationexercise.api.product_api import ProductApi
from sites.automationexercise.api.user_api import UserApi
from common.faker_util import random_user
from common.logger import get_logger
from sites.automationexercise.pages.home_page import HomePage
from sites.automationexercise.pages.login_page import LoginPage
from sites.automationexercise.pages.products_page import ProductsPage
from sites.automationexercise.pages.cart_page import CartPage

log = get_logger("automationexercise")

# 本目录下的用例拿到的 cfg 都是这个站的，不管命令行 --site 选了谁
cfg = site_cfg("automationexercise")


# ===============================================================
# 接口客户端
#   session 级：整个测试过程复用同一个 requests.Session，
#   保持连接池，速度更快
# ===============================================================
@pytest.fixture(scope="session")
def product_api(cfg):
    return ProductApi(cfg)


@pytest.fixture(scope="session")
def user_api(cfg):
    return UserApi(cfg)


# ===============================================================
# 页面对象
#   function 级：每个用例拿到全新的页面，互不干扰
# ===============================================================
@pytest.fixture
def home_page(page, cfg):
    return HomePage(page, cfg).open()


@pytest.fixture
def login_page(page, cfg):
    return LoginPage(page, cfg).open()


@pytest.fixture
def products_page(page, cfg):
    return ProductsPage(page, cfg).open()


@pytest.fixture
def cart_page(page, cfg):
    return CartPage(page, cfg).open()


# ===============================================================
# 测试数据管理
#
# ★ 面试重点：自动化的测试数据怎么管 ★
#
#   反面做法：在被测系统里手工建一个账号，写死在配置里
#       问题：账号状态会被别人改、数据会脏、并行执行会抢账号
#
#   正确做法：用例自己造数据，用完自己清理
#       yield 前 = setup（造数据）
#       yield 后 = teardown（清数据）
#       无论用例成功还是失败，teardown 都会执行
# ===============================================================
@pytest.fixture(scope="function")
def temp_user(user_api):
    """临时账号：注册 -> 用例使用 -> 自动删除。"""
    user = random_user()
    user_api.create_account(user)
    log.info("已创建临时账号: %s", user["email"])

    yield user

    try:
        user_api.delete_account(user["email"], user["password"])
        log.info("已清理临时账号: %s", user["email"])
    except Exception as exc:
        log.warning("清理账号失败 %s: %s", user["email"], exc)


# ===============================================================
# 环境可用性前置检查
#
# ★ 为什么要有这个（面试可讲）★
#   被测站点有机器人防护，跑得太频繁会把 IP 临时封掉，返回 403。
#   如果不做这个检查，54 条用例会全部失败，报告里一片红，
#   看报告的人会以为系统崩了，实际只是自动化机器被拦了。
#
#   框架的责任是：区分「产品缺陷」和「环境问题」。
#   环境不可用时，用例应该 SKIP（跳过）而不是 FAIL（失败），
#   并且在报告里写清原因。
# ===============================================================
@pytest.fixture(scope="session", autouse=True)
def _site_reachable(cfg):
    """整个测试开始前，先确认被测站点可用（通用逻辑在 plugins/site_plugin.probe）。"""
    probe(cfg, "/productsList")
