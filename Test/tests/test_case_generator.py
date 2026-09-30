# -*- coding: utf-8 -*-
"""巡检用例自动生成的自测。"""

import pytest
import yaml

from tools.case_generator import CaseGenerator, _cid, _short
from tools.sitemap import Node, Sitemap


@pytest.fixture
def sitemap():
    sm = Sitemap("http://x.com", "test")
    a = Node("http://x.com/", "首页")
    a.links = [{"href": "http://x.com/a"}, {"href": ""}]
    a.apis = [{"method": "GET", "url": "http://x.com/api/1"}]
    b = Node("http://x.com/static/x.js", "静态资源")
    c = Node("http://x.com/坏页面", "打不开的页面")
    c.error = "导航超时"
    sm.add(a)
    sm.add(b)
    sm.add(c)
    return sm


@pytest.fixture
def gen(sandbox, make_cfg):
    def _gen(rules=None, **cfg):
        base = {"base_url": "http://x.com", "case_gen": {"max_per_kind": 200}}
        base.update(cfg)
        return CaseGenerator(make_cfg(base),
                             rules={"skip_url_patterns": ["/static/"],
                                    "forbidden_text": ["Traceback"]}
                             if rules is None else rules)
    return _gen


class TestHelpers:

    def test_用例ID稳定可复现(self):
        # 不稳定的话每次重新爬站，人工改过的 enabled 全丢
        assert _cid("smoke", "http://x.com/a") == _cid("smoke", "http://x.com/a")

    def test_不同输入生成不同ID(self):
        assert _cid("smoke", "a") != _cid("smoke", "b")
        assert _cid("smoke", "a") != _cid("link", "a")

    @pytest.mark.parametrize("url,expected", [
        ("http://x.com/", "首页"),
        ("http://x.com", "首页"),
        ("http://x.com/a/b", "a_b"),
    ])
    def test_URL缩写(self, url, expected):
        assert _short(url) == expected

    def test_URL缩写有长度上限(self):
        assert len(_short("http://x.com/" + "a" * 100)) == 40


class TestGenerate:

    def test_三类用例都生成(self, gen, sitemap):
        cases = gen().generate(sitemap)
        assert set(cases) == {"smoke", "link", "api"}

    def test_跳过静态资源(self, gen, sitemap):
        urls = [c["url"] for c in gen().gen_smoke(sitemap)]
        assert "http://x.com/static/x.js" not in urls

    def test_跳过爬取时就出错的页面(self, gen, sitemap):
        # 页面本来就没爬下来，生成的用例必然失败，属于噪声
        urls = [c["url"] for c in gen().gen_smoke(sitemap)]
        assert "http://x.com/坏页面" not in urls

    def test_冒烟用例带上禁止出现的文案(self, gen, sitemap):
        assert gen().gen_smoke(sitemap)[0]["forbidden_text"] == ["Traceback"]

    def test_链接用例过滤掉空href(self, gen, sitemap):
        assert gen().gen_link(sitemap)[0]["links"] == ["http://x.com/a"]

    def test_没有链接的页面不生成链接用例(self, gen, sitemap):
        assert len(gen().gen_link(sitemap)) == 1

    def test_接口用例记录来源页面(self, gen, sitemap):
        assert gen().gen_api(sitemap)[0]["from_page"] == "http://x.com/"

    def test_接口用例带上预期状态码和耗时上限(self, gen, sitemap):
        case = gen().gen_api(sitemap)[0]
        assert case["expect_status"] == [200, 201, 204]
        assert case["max_ms"] == 5000

    def test_数量上限生效(self, gen):
        sm = Sitemap()
        for i in range(10):
            sm.add(Node("http://x.com/%d" % i, "P%d" % i))
        g = gen(case_gen={"max_per_kind": 3})
        assert len(g.gen_smoke(sm)) == 3

    def test_规则为空时不跳过任何页面(self, gen, sitemap):
        urls = [c["url"] for c in gen(rules={}).gen_smoke(sitemap)]
        assert "http://x.com/static/x.js" in urls


class TestSave:

    def test_写出yaml文件(self, gen, sitemap, sandbox):
        g = gen()
        info = g.save(g.generate(sitemap))
        data = yaml.safe_load(open(info["path"], encoding="utf-8"))
        assert data["base_url"] == "http://x.com"
        assert "smoke" in data["cases"]

    def test_新生成的用例默认启用(self, gen, sitemap):
        g = gen()
        cases = g.generate(sitemap)
        g.save(cases)
        assert cases["smoke"][0]["enabled"] is True

    def test_重新生成时保留人工关掉的用例(self, gen, sitemap):
        # 不保留的话，每次重爬人工关掉的用例又会全被打开
        g = gen()
        first = g.generate(sitemap)
        g.save(first)

        path = g.save(first)["path"]
        data = yaml.safe_load(open(path, encoding="utf-8"))
        data["cases"]["smoke"][0]["enabled"] = False
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True)

        second = g.generate(sitemap)
        info = g.save(second)
        assert second["smoke"][0]["enabled"] is False
        assert info["kept"] > 0

    def test_首次保存全部算新增(self, gen, sitemap):
        g = gen()
        info = g.save(g.generate(sitemap))
        assert info["added"] > 0 and info["kept"] == 0

    def test_已有文件损坏时当作没有旧数据(self, gen, sitemap, sandbox):
        (sandbox / "data" / "crawl_cases.yaml").write_text(
            "\t不是合法 yaml: [", encoding="utf-8")
        g = gen()
        assert g.save(g.generate(sitemap))["kept"] == 0


class TestThirdPartyFilter:
    """
    ★ 回归用例：钉住一个把巡检报告变成废纸的 bug ★

    页面上挂着 Google 广告，浏览器会替广告脚本发一堆 XHR。
    这些请求原来会被当成「本站接口」采集下来 ——
    实测 126 条接口用例里 125 条是 doubleclick / googlesyndication，
    真正属于被测系统的只有 1 条。
    """

    def _sm(self):
        sm = Sitemap("https://本站.com", "test")
        n = Node("https://本站.com/", "首页")
        n.apis = [
            {"method": "GET", "url": "https://本站.com/api/products"},
            {"method": "GET", "url": "https://googleads.g.doubleclick.net/x"},
            {"method": "POST", "url": "https://pagead2.googlesyndication.com/y"},
            {"method": "GET", "url": "https://static.enzymic.co/z"},
        ]
        sm.add(n)
        return sm

    def test_只保留本站接口(self, gen):
        urls = [c["url"] for c in gen(base_url="https://本站.com").gen_api(self._sm())]
        assert urls == ["https://本站.com/api/products"]

    def test_站点地图没记根地址时退回配置里的base_url(self, gen):
        sm = self._sm()
        sm.root_url = ""
        urls = [c["url"] for c in gen(base_url="https://本站.com").gen_api(sm)]
        assert urls == ["https://本站.com/api/products"]
