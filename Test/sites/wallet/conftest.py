# -*- coding: utf-8 -*-
"""钱包站的 fixture。被测对象是本地假服务 sites/wallet/mock.py，不联网，所以不用探测站点可用性。"""

import pytest

from plugins.site_plugin import site_cfg

cfg = site_cfg("wallet")


@pytest.fixture(scope="module")
def wallet_url():
    """钱包服务。每个模块起一个，模块结束就关。"""
    from sites.wallet.mock import Routes
    from tools.mock_server import MockServer
    with MockServer(Routes) as srv:
        yield srv.url


@pytest.fixture
def wallet(cfg, wallet_url):
    """一个全新用户的钱包，余额从 0 开始。"""
    from sites.wallet.api.wallet_api import WalletApi
    return WalletApi(cfg, wallet_url)
