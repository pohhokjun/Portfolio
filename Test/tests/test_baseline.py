# -*- coding: utf-8 -*-
"""基线管理的自测（视觉基线 + 接口结构基线）。

基线机制的关键行为只有三条，但每一条错了都会造成大面积假结果：
    没有基线 -> 建立并通过（不能报失败，否则第一次跑全红）
    有基线且一致 -> 通过
    有基线且不一致 -> 失败（不能静默通过，否则视觉回归形同虚设）
"""

import pytest

from common.baseline import BaselineStore, safe_name, schema_of

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


@pytest.fixture
def store(sandbox, make_cfg):
    def _store(**visual):
        conf = {"auto_create": True, "diff_threshold": 0.02,
                "pixel_threshold": 30, "ignore_boxes": {}}
        conf.update(visual)
        return BaselineStore(make_cfg({"visual": conf}))
    return _store


class TestSafeName:

    @pytest.mark.parametrize("raw,expected", [
        ("a/b", "a_b"),
        ("测试 用例", "测试_用例"),
        ("a:b*c?", "a_b_c"),
        ("__a__", "a"),
        ("", "x"),
        ("///", "x"),
    ])
    def test_转成安全文件名(self, raw, expected):
        assert safe_name(raw) == expected

    def test_中文要保留不能被吃掉(self):
        # 全转成下划线的话，所有中文用例名会撞成同一个文件
        assert safe_name("首页") == "首页"


class TestImageBaseline:

    def test_第一次跑自动建基线并通过(self, store, png):
        res = store().compare_image("c1", "home", png("cur"))
        assert res["status"] == "created"

    def test_关掉自动建基线时报缺失(self, store, png):
        res = store(auto_create=False).compare_image("c1", "home", png("cur"))
        assert res["status"] == "missing"

    def test_第二次一致判same(self, store, png):
        s = store()
        s.compare_image("c1", "home", png("a", color=WHITE))
        res = s.compare_image("c1", "home", png("b", color=WHITE))
        assert res["status"] == "same"
        assert res["message"] == ""

    def test_差异超阈值判changed并说明原因(self, store, png):
        s = store()
        s.compare_image("c1", "home", png("a", color=WHITE))
        res = s.compare_image("c1", "home", png("b", color=BLACK))
        assert res["status"] == "changed"
        assert "超过阈值" in res["message"]

    def test_差异在阈值内仍判same(self, store, png):
        # 40x40 改 4x40=160 像素 = 10%
        s = store(diff_threshold=0.5)
        s.compare_image("c1", "home", png("a", size=(40, 40), color=WHITE))
        res = s.compare_image("c1", "home",
                              png("b", size=(40, 40), color=WHITE,
                                  boxes=[((0, 0, 4, 40), BLACK)]))
        assert res["status"] == "same"

    def test_尺寸变了要报出来(self, store, png):
        s = store()
        s.compare_image("c1", "home", png("a", size=(40, 40)))
        res = s.compare_image("c1", "home", png("b", size=(40, 80)))
        assert res["status"] == "changed"
        assert "尺寸不一致" in res["message"]

    def test_ignore_boxes按case_id生效(self, store, png):
        s = store(ignore_boxes={"c1": [[0, 0, 40, 40]]})
        s.compare_image("c1", "home", png("a", size=(40, 40), color=WHITE))
        res = s.compare_image("c1", "home", png("b", size=(40, 40), color=BLACK))
        assert res["status"] == "same"

    def test_ignore_boxes的星号对所有用例生效(self, store, png):
        s = store(ignore_boxes={"*": [[0, 0, 40, 40]]})
        s.compare_image("随便什么", "home", png("a", size=(40, 40), color=WHITE))
        res = s.compare_image("随便什么", "home", png("b", size=(40, 40), color=BLACK))
        assert res["status"] == "same"

    def test_不同case_id的同名基线互不干扰(self, store, png):
        s = store()
        s.compare_image("c1", "home", png("a", color=WHITE))
        # c2 是新的用例，即使 name 一样也该走「建立基线」
        assert s.compare_image("c2", "home", png("b", color=BLACK))["status"] == "created"

    def test_更新基线后再比就一致了(self, store, png):
        s = store()
        s.compare_image("c1", "home", png("a", color=WHITE))
        black = png("b", color=BLACK)
        s.update_image("c1", "home", black)
        assert s.compare_image("c1", "home", black)["status"] == "same"

    def test_has能判断基线在不在(self, store, png):
        s = store()
        assert s.has("c1", "home") is False
        s.compare_image("c1", "home", png("a"))
        assert s.has("c1", "home") is True


class TestDataBaseline:

    def test_第一次保存结构(self, store):
        assert store().compare_data("api", "products", {"a": "int"})["status"] == "created"

    def test_结构不变判same(self, store):
        s = store()
        s.compare_data("api", "products", {"a": "int"})
        assert s.compare_data("api", "products", {"a": "int"})["status"] == "same"

    def test_结构变了列出每一处(self, store):
        s = store()
        s.compare_data("api", "products", {"a": "int", "b": "str"})
        res = s.compare_data("api", "products", {"a": "str"})
        assert res["status"] == "changed"
        assert {c["path"] for c in res["changes"]} == {"a", "b"}

    def test_关掉自动建基线时报缺失(self, store):
        assert store(auto_create=False).compare_data(
            "api", "x", {"a": 1})["status"] == "missing"


class TestSchemaOf:

    def test_只保留字段名和类型丢掉具体值(self):
        assert schema_of({"id": 1, "name": "x"}) == {"id": "int", "name": "str"}

    def test_列表只取第一个元素做样本(self):
        assert schema_of([{"a": 1}, {"a": 2}]) == [{"a": "int"}]

    def test_空列表(self):
        assert schema_of([]) == []

    def test_None的类型是NoneType(self):
        assert schema_of({"a": None}) == {"a": "NoneType"}

    def test_嵌套太深会截断防止无限递归(self):
        deep = {"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}}
        assert "..." in str(schema_of(deep))

    def test_字段顺序变了不算结构变化(self):
        # 字典是无序的，接口字段换个顺序不该报警
        assert schema_of({"b": 1, "a": 2}) == schema_of({"a": 2, "b": 1})


class TestMaintenance:

    def test_列出全部基线(self, store, png):
        s = store()
        s.compare_image("c1", "home", png("a"))
        s.compare_data("c2", "api", {"a": 1})
        rows = {r["case"]: r for r in s.list_all()}
        assert rows["c1"]["images"] == 1
        assert rows["c2"]["data"] == 1

    def test_prune删掉不在保留名单里的基线(self, store, png):
        s = store()
        s.compare_image("要留的", "home", png("a"))
        s.compare_image("要删的", "home", png("b"))
        assert s.prune(["要留的"]) == 1
        assert [r["case"] for r in s.list_all()] == ["要留的"]

    def test_prune保留名单为空就全删(self, store, png):
        s = store()
        s.compare_image("c1", "home", png("a"))
        assert s.prune([]) == 1
        assert s.list_all() == []
