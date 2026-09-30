# -*- coding: utf-8 -*-
"""
账号池插件

【来源】原 17_测试/core/account_pool.py，改造成 pytest fixture。

★ 解决并行执行抢账号的问题 ★

用法：
    def test_admin_feature(self, account):
        # account 是自动租借来的空闲账号，用例结束自动归还
        login(account["username"], account["password"])

    # 需要特定角色：
    @pytest.mark.account_role("admin")
    def test_admin_only(self, account):
        ...

配置在 站点 site.yaml 的 accounts 段。
如果没配置账号，fixture 会跳过用例而不是报错。
"""

import pytest

from common.account_pool import AccountPool, NoAccountAvailable
from common.logger import get_logger

log = get_logger("account.plugin")


@pytest.fixture(scope="session")
def account_pool(cfg):
    pool = AccountPool(cfg)
    yield pool
    pool.release_all()


@pytest.fixture
def account(request, account_pool):
    """
    租借一个账号，用例结束自动归还。

    可以用 marker 指定角色：
        @pytest.mark.account_role("admin")
    """
    marker = request.node.get_closest_marker("account_role")
    role = marker.args[0] if marker and marker.args else None

    if not account_pool.accounts:
        pytest.skip("未配置账号池，请在 站点 site.yaml 的 accounts 段添加账号")

    try:
        acc = account_pool.acquire(role=role)
    except NoAccountAvailable as exc:
        pytest.skip("账号池不可用: %s" % exc)
        return

    log.debug("用例 %s 租借账号 %s", request.node.name, acc.get("username"))
    yield acc
    account_pool.release(acc)
