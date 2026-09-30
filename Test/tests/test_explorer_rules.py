# -*- coding: utf-8 -*-
"""爬虫边界规则的自测。

★ 这一组是整个项目里最不能出错的用例 ★

    爬虫在测试环境乱点，会把测试数据删光；
    在生产环境乱点，那是事故。
    danger_keywords 黑名单是唯一的安全底线，
    所以每一条都要有用例钉死，谁也别想不小心把它改坏。
"""

import pytest

from config.settings import load_rules
from tools.explorer import SiteExplorer

ROOT = "https://本站.com"


@pytest.fixture
def explorer(make_cfg):
    def _explorer(rules=None, **cfg):
        base = {"base_url": ROOT, "explore": {}}
        base.update(cfg)
        return SiteExplorer(make_cfg(base),
                            rules=load_rules("explore_rules") if rules is None
                            else rules)
    return _explorer


class TestDangerBlacklist:

    @pytest.mark.parametrize("path", [
        "/delete_account", "/user/delete/1", "/order/remove",
        "/data/destroy", "/password/reset", "/wallet/withdraw",
        "/payout/apply", "/order/cancel",
        "/账户/删除", "/购物车/清空", "/账号/注销", "/余额/提现",
    ])
    def test_危险链接一律不访问(self, explorer, path):
        assert explorer()._allowed(ROOT + path, ROOT) is False

    def test_大小写混写也拦得住(self, explorer):
        assert explorer()._allowed(ROOT + "/DELETE_Account", ROOT) is False

    def test_正常链接放行(self, explorer):
        for path in ("/products", "/login", "/view_cart", "/product_details/1"):
            assert explorer()._allowed(ROOT + path, ROOT) is True


class TestScopeRules:

    def test_站外链接不爬(self, explorer):
        # 爬到站外就等于在压测别人家的服务器
        assert explorer()._allowed("https://别人家.com/a", ROOT) is False

    def test_子域名也算站外(self, explorer):
        assert explorer()._allowed("https://blog.本站.com/a", ROOT) is False

    def test_exclude里的路径不爬(self, explorer):
        # 爬到 /logout 会把自己的登录态搞掉，后面的页面全爬不动
        assert explorer()._allowed(ROOT + "/logout", ROOT) is False

    def test_include限定后只爬指定范围(self, explorer):
        e = explorer(rules={"include_patterns": ["/api/"]})
        assert e._allowed(ROOT + "/api/x", ROOT) is True
        assert e._allowed(ROOT + "/products", ROOT) is False

    def test_include为空表示不限制(self, explorer):
        assert explorer(rules={})._allowed(ROOT + "/任意路径", ROOT) is True

    @pytest.mark.parametrize("ext", ["pdf", "zip", "png", "jpg", "css", "js",
                                     "mp4", "exe", "xlsx"])
    def test_静态资源和下载链接不爬(self, explorer, ext):
        assert explorer()._allowed("%s/f.%s" % (ROOT, ext), ROOT) is False

    def test_没有扩展名的路径正常放行(self, explorer):
        assert explorer()._allowed(ROOT + "/products", ROOT) is True

    def test_查询串里带点号不会被误判成静态资源(self, explorer):
        assert explorer()._allowed(ROOT + "/search?q=a.png", ROOT) is True


class TestConfigDefaults:

    def test_没配explore段时用内置默认值(self, explorer):
        e = explorer(explore={})
        assert e.max_pages == 30 and e.max_depth == 2 and e.delay == 0.8

    def test_配置生效(self, explorer):
        e = explorer(explore={"max_pages": 5, "max_depth": 1, "delay": 0})
        assert (e.max_pages, e.max_depth, e.delay) == (5, 1, 0.0)

    def test_yaml里写成字符串也能转(self, explorer):
        assert explorer(explore={"max_pages": "7"}).max_pages == 7
