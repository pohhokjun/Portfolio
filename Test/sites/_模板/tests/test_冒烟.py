# -*- coding: utf-8 -*-
"""示例用例：首页能打开、有标题。复制后按这个站的业务改。"""

import pytest


@pytest.mark.smoke
def test_首页能打开(page, cfg):
    page.goto(cfg.base_url)
    assert page.title()
