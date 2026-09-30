# -*- coding: utf-8 -*-
"""站点地图数据结构的自测。

URL 归一化写错的后果很具体：同一个页面被当成好几个，
爬虫在原地打转，25 页的上限全浪费在重复页面上。
"""

import pytest

from tools.sitemap import Node, Sitemap, default_path, normalize, same_site


class TestNormalize:

    @pytest.mark.parametrize("raw,expected", [
        ("http://x.com/a#锚点", "http://x.com/a"),
        ("http://x.com/a/", "http://x.com/a"),
        ("  http://x.com/a  ", "http://x.com/a"),
        ("http://x.com/", "http://x.com/"),          # 根路径的斜杠要留着
    ])
    def test_归一化(self, raw, expected):
        assert normalize(raw) == expected

    def test_相对路径要拼上base(self):
        assert normalize("/b", base="http://x.com/a") == "http://x.com/b"

    def test_strip_query去掉查询串(self):
        url = "http://x.com/a?id=1"
        assert normalize(url, strip_query=True) == "http://x.com/a"
        assert normalize(url, strip_query=False) == url

    def test_空值返回空串(self):
        assert normalize("") == "" and normalize(None) == ""

    def test_同一页面的几种写法归一化后相等(self):
        # 这才是归一化真正要保证的事
        base = "http://x.com/list"
        assert (normalize("http://x.com/a/#top", base) ==
                normalize("http://x.com/a/", base) ==
                normalize("/a", base))


class TestSameSite:

    def test_同域名为真(self):
        assert same_site("http://x.com/a", "http://x.com") is True

    def test_不同域名为假(self):
        assert same_site("http://y.com/a", "http://x.com") is False

    def test_子域名算不同站(self):
        assert same_site("http://a.x.com", "http://x.com") is False

    def test_非法输入不崩(self):
        assert same_site(None, "http://x.com") is False


class TestNode:

    def test_序列化再反序列化数据不丢(self):
        n = Node("http://x.com/a", "标题", depth=2, source="http://x.com")
        n.status = 200
        n.load_ms = 120
        n.links = [{"href": "http://x.com/b"}]
        n.forms = [{"action": "/login"}]
        n.apis = [{"method": "GET", "url": "http://x.com/api/1"}]
        n.console_errors = ["boom"]
        n.error = "超时"
        assert Node.from_dict(n.to_dict()).to_dict() == n.to_dict()

    def test_从空字典还原也有合理默认值(self):
        n = Node.from_dict({})
        assert n.url == "" and n.links == [] and n.status is None


class TestSitemap:

    def _sm(self):
        sm = Sitemap("http://x.com", "test")
        a = Node("http://x.com/a", "A", depth=0)
        a.apis = [{"method": "GET", "url": "http://x.com/api/1"}]
        a.forms = [{"action": "/login"}]
        a.links = [{"href": "http://x.com/b"}]
        b = Node("http://x.com/b", "B", depth=1)
        b.apis = [{"method": "GET", "url": "http://x.com/api/1"},   # 重复
                  {"method": "POST", "url": "http://x.com/api/1"}]  # 方法不同
        sm.add(a)
        sm.add(b)
        return sm

    def test_同URL重复add会覆盖不会变成两个(self):
        sm = Sitemap()
        sm.add(Node("http://x.com/a", "旧"))
        sm.add(Node("http://x.com/a", "新"))
        assert len(sm.nodes) == 1
        assert sm.nodes["http://x.com/a"].title == "新"

    def test_接口按方法加URL去重(self):
        assert len(self._sm().all_apis()) == 2

    def test_接口带上是在哪个页面发现的(self):
        # 巡检失败时得知道从哪进去才会触发这个接口
        apis = {a["method"]: a for a in self._sm().all_apis()}
        assert apis["GET"]["page"] == "http://x.com/a"
        assert apis["POST"]["page"] == "http://x.com/b"

    def test_去重不能改到原始节点上(self):
        sm = self._sm()
        sm.all_apis()
        assert "page" not in sm.nodes["http://x.com/a"].apis[0]

    def test_表单带上所属页面(self):
        forms = self._sm().all_forms()
        assert forms[0]["page"] == "http://x.com/a"

    def test_保存后能原样读回来(self, sandbox):
        path = self._sm().save()
        loaded = Sitemap.load(path)
        assert set(loaded.nodes) == {"http://x.com/a", "http://x.com/b"}
        assert loaded.root_url == "http://x.com"

    def test_保存到指定路径会自动建父目录(self, sandbox):
        path = self._sm().save(sandbox / "新目录" / "sm.json")
        assert Sitemap.load(path).env == "test"

    def test_树状文本按深度缩进(self):
        text = self._sm().tree_text()
        assert "- A" in text and "  - B" in text

    def test_树状文本超过上限会截断(self):
        sm = Sitemap()
        for i in range(10):
            sm.add(Node("http://x.com/%d" % i, "P%d" % i))
        text = sm.tree_text(max_nodes=3)
        assert "其余 7 个页面省略" in text

    def test_默认路径按环境区分(self, sandbox):
        assert str(default_path("test")) != str(default_path("prod"))
