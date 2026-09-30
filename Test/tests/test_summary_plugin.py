# -*- coding: utf-8 -*-
"""
测试总结报告插件的自测。

这份报告是交出去给人看的，算错了比不出报告更糟 ——
「通过率 100%」写在报告上，没人会再去核对。
所以统计口径和结论判定必须有用例钉死。
"""

import pytest

from plugins import summary_plugin as S


class FakeReport:
    """够用就好的假 report：只实现被统计代码真正会碰的成员。"""

    def __init__(self, nodeid, when="call", outcome="passed",
                 wasxfail=None, longrepr=None):
        self.nodeid = nodeid
        self.when = when
        self.outcome = outcome
        self.longrepr = longrepr
        if wasxfail is not None:
            self.wasxfail = wasxfail

    @property
    def passed(self):
        return self.outcome == "passed"

    @property
    def failed(self):
        return self.outcome == "failed"

    @property
    def skipped(self):
        return self.outcome == "skipped"


@pytest.fixture
def collector():
    return S._Collector()


class TestLayerMapping:

    @pytest.mark.parametrize("nodeid,expected", [
        ("tests/test_diff.py::test_x", "框架自测"),
        ("testcases/quality/test_a11y.py::test_x", "质量属性"),
        ("sites/automationexercise/tests/ui/test_login.py::test_x", "UI 功能"),
        ("sites/automationexercise/tests/api/test_contract.py::test_x", "接口与契约"),
        ("sites/automationexercise/tests/perf/test_p.py::test_x", "接口性能"),
        ("sites/automationexercise/tests/security/test_s.py::test_x", "安全"),
        ("sites/automationexercise/tests/visual/test_v.py::test_x", "视觉回归"),
        ("testcases/crawl/test_c.py::test_x", "站点巡检"),
        ("somewhere/else.py::test_x", "其他"),
    ])
    def test_按路径归层(self, nodeid, expected):
        assert S._layer_of(nodeid) == expected

    def test_Windows反斜杠路径也能归层(self):
        # pytest 在 Windows 上给的 nodeid 是反斜杠，不处理就全掉进「其他」
        assert S._layer_of("sites\\automationexercise\\tests\\ui\\test_login.py::test_x") == "UI 功能"


class TestReadableNodeId:
    """pytest 会把中文参数名转义，报告里得还原回来。"""

    def test_还原中文参数名(self):
        raw = "test_x[\\u5546\\u54c1\\u5217\\u8868]"
        assert S._readable(raw) == "test_x[商品列表]"

    def test_纯英文不受影响(self):
        assert S._readable("test_x[chromium]") == "test_x[chromium]"

    def test_多段转义都能还原(self):
        raw = "test_x[\\u624b\\u673a-\\u9996\\u9875]"
        assert S._readable(raw) == "test_x[手机-首页]"

    def test_乱码不崩只是原样返回(self):
        weird = "test_x[\\uZZZZ]"
        assert S._readable(weird) == weird


class TestCollector:

    def test_通过(self, collector):
        collector.record(FakeReport("a", "call", "passed"))
        assert collector.rows["a"][0] == "passed"

    def test_失败(self, collector):
        collector.record(FakeReport("a", "call", "failed"))
        assert collector.rows["a"][0] == "failed"

    def test_setup挂了算异常不算失败(self, collector):
        # error 通常是环境/前置问题，failed 才是被测系统的问题，
        # 混在一起统计会误导看报告的人
        collector.record(FakeReport("a", "setup", "failed"))
        assert collector.rows["a"][0] == "error"

    def test_setup跳过算跳过(self, collector):
        collector.record(FakeReport("a", "setup", "skipped"))
        assert collector.rows["a"][0] == "skipped"

    def test_xfail不算失败(self, collector):
        collector.record(FakeReport("a", "call", "skipped", wasxfail="已知缺陷"))
        assert collector.rows["a"][0] == "xfailed"

    def test_xpass单独统计(self, collector):
        # 已知缺陷突然通过了，说明对方修好了，该去摘掉登记
        collector.record(FakeReport("a", "call", "passed", wasxfail="已知缺陷"))
        assert collector.rows["a"][0] == "xpassed"

    def test_teardown挂了也要记(self, collector):
        collector.record(FakeReport("a", "teardown", "failed"))
        assert collector.rows["a"][0] == "error"

    def test_call阶段的结果覆盖setup(self, collector):
        collector.record(FakeReport("a", "setup", "passed"))
        collector.record(FakeReport("a", "call", "failed"))
        assert collector.rows["a"][0] == "failed"

    def test_teardown不会覆盖已有结果(self, collector):
        # 用例本身失败了，teardown 又挂了 —— 该报「失败」不是「异常」
        collector.record(FakeReport("a", "call", "failed"))
        collector.record(FakeReport("a", "teardown", "failed"))
        assert collector.rows["a"][0] == "failed"


class TestBar:

    def test_全通过是一整条(self, ):
        assert S._bar(10, 0, 0, 0, 0).count("<i") == 1

    def test_各种状态各占一段(self):
        assert S._bar(5, 2, 1, 1, 1).count("<i") == 4

    def test_零的段不画(self):
        assert 'width:0' not in S._bar(5, 0, 0, 0, 0)

    def test_全零不除零崩溃(self):
        assert S._bar(0, 0, 0, 0, 0) == ""


class TestLists:

    def test_没有失败时给一句话不是空表格(self):
        assert "没有失败用例" in S._fail_list({})

    def test_失败清单带上报错最后一行(self):
        rep = FakeReport("sites/automationexercise/tests/ui/t.py::test_x", "call", "failed",
                         longrepr="一堆堆栈\nE   AssertionError: 金额算错了")
        out = S._fail_list({"sites/automationexercise/tests/ui/t.py::test_x": ("failed", rep)})
        assert "金额算错了" in out and "失败" in out

    def test_失败清单里的中文用例名要还原(self):
        nid = "t.py::test_x[\\u5546\\u54c1\\u5217\\u8868]"
        out = S._fail_list({nid: ("failed", FakeReport(nid, "call", "failed"))})
        assert "商品列表" in out

    def test_报错为空也不崩(self):
        rep = FakeReport("t.py::test_x", "call", "failed", longrepr=None)
        assert "test_x" in S._fail_list({"t.py::test_x": ("failed", rep)})

    def test_没有已知缺陷时给一句话(self):
        assert "没有登记在案" in S._known_list({})

    def test_已知缺陷清单带上登记原因(self):
        rep = FakeReport("t.py::test_x", "call", "skipped",
                         wasxfail="reason: 违反 WCAG 2.1.1")
        out = S._known_list({"t.py::test_x": ("xfailed", rep)})
        assert "WCAG 2.1.1" in out
        assert "reason: " not in out      # 前缀要去掉

    def test_HTML特殊字符要转义(self):
        # 报错信息里带 <script> 的话，不转义就会破坏报告结构
        rep = FakeReport("t.py::test_x", "call", "failed",
                         longrepr="E  <script>alert(1)</script>")
        out = S._fail_list({"t.py::test_x": ("failed", rep)})
        assert "<script>" not in out and "&lt;script&gt;" in out
