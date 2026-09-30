# -*- coding: utf-8 -*-
"""restful-booker 站的 fixture。"""

import pytest

from plugins.site_plugin import probe, site_cfg

cfg = site_cfg("restful_booker")


@pytest.fixture(scope="session", autouse=True)
def _site_reachable(cfg):
    probe(cfg, "/ping")
