# -*- coding: utf-8 -*-
"""
testcases 层级的 conftest.py —— 通用用例（对任意站点都成立的检查）

这里的用例不认识任何具体站点：测谁由 --site 决定，
验收点（页面清单、选择器、要不要登录）来自 sites/<站>/site.yaml 的 profile。
站点专属的 fixture 放在 sites/<站>/conftest.py。
"""

import pytest

from plugins.site_plugin import probe


@pytest.fixture(scope="session", autouse=True)
def _site_reachable(request, cfg):
    """整组开跑前确认 --site 选的站点可用；--mock 时接口走本地假服务，不用探测。"""
    if not request.config.getoption("--mock"):
        probe(cfg)
