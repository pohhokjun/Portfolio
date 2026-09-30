# -*- coding: utf-8 -*-
"""
通用接口层（框架容错：故障注入）的 conftest.py

站点的接口客户端在 sites/<站>/conftest.py；这里只放「只有这个目录需要」的东西。
它同时也是一个演示：conftest 可以按目录层层细分。
"""

import pytest


@pytest.fixture(autouse=True, scope="function")
def _api_case_banner(request):
    """
    autouse=True 表示不用在用例里声明，自动对本目录所有用例生效。

    典型用途：统一打印用例分隔线、统一初始化、统一埋点。
    面试问「autouse 什么时候用」，答：所有用例都需要的横切逻辑。
    """
    yield
