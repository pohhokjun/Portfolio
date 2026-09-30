# -*- coding: utf-8 -*-
"""断言模块的自测。

断言是测试框架里最不能出错的一块：
断言写错了，用例「通过」也没有任何意义 —— 这叫假阴性，
比用例直接报错危险得多，因为没人会去查一条绿色的用例。
"""

import pytest

from common import assertions as A
from common.assertions import SoftAssert


class TestHardAssert:

    def test_相等通过(self):
        A.assert_equal(1, 1, "数字")

    def test_不相等抛异常且带上期望和实际(self):
        with pytest.raises(AssertionError) as e:
            A.assert_equal(1, 2, "数字")
        msg = str(e.value)
        assert "数字" in msg and "1" in msg and "2" in msg

    def test_包含(self):
        A.assert_in("a", "abc")
        with pytest.raises(AssertionError):
            A.assert_in("z", "abc")

    def test_不包含(self):
        A.assert_not_in("z", "abc")
        with pytest.raises(AssertionError):
            A.assert_not_in("a", "abc")

    def test_为真(self):
        A.assert_true(1)
        with pytest.raises(AssertionError):
            A.assert_true(0)

    def test_状态码可以传单个值(self):
        A.assert_status_code(200, 200)
        with pytest.raises(AssertionError):
            A.assert_status_code(500, 200)

    def test_状态码可以传一组允许值(self):
        A.assert_status_code(204, [200, 201, 204])
        with pytest.raises(AssertionError):
            A.assert_status_code(404, [200, 201, 204])

    def test_小于(self):
        A.assert_less_than(100, 200)
        with pytest.raises(AssertionError):
            A.assert_less_than(300, 200)

    def test_小于收到None要判失败而不是崩在比较上(self):
        # 接口没返回耗时的时候，None < 200 在 Python3 里是 TypeError，
        # 那样报出来的错完全看不懂问题在哪
        with pytest.raises(AssertionError):
            A.assert_less_than(None, 200)


class TestSoftAssert:

    def test_全部通过时不抛(self):
        sa = SoftAssert()
        sa.equal(1, 1, "a")
        sa.true(True, "b")
        sa.assert_all()
        assert sa.checks == 2 and sa.failures == []

    def test_收集全部失败而不是第一个就停(self):
        # 这就是软断言存在的意义：一轮暴露所有问题
        sa = SoftAssert()
        sa.equal(1, 2, "第一个")
        sa.equal(3, 4, "第二个")
        sa.equal(5, 5, "第三个")
        with pytest.raises(AssertionError) as e:
            sa.assert_all()
        msg = str(e.value)
        assert "第一个" in msg and "第二个" in msg
        assert "3 个检查点" in msg and "2 个失败" in msg

    def test_每个检查方法都返回布尔值(self):
        # 返回值要能拿来做流程控制： if not sa.true(...): return
        sa = SoftAssert()
        assert sa.true(True, "x") is True
        assert sa.equal(1, 2, "x") is False
        assert sa.not_equal(1, 2, "x") is True
        assert sa.contains("abc", "a", "x") is True
        assert sa.not_contains("abc", "z", "x") is True
        assert sa.status_code(200, [200], "x") is True
        assert sa.less_than(1, 2, "x") is True

    def test_haystack是None时按空串处理不崩(self):
        sa = SoftAssert()
        assert sa.contains(None, "a", "x") is False
        assert sa.not_contains(None, "a", "x") is True

    def test_less_than收到None判失败(self):
        sa = SoftAssert()
        assert sa.less_than(None, 100, "耗时") is False

    def test_不调assert_all失败会被吞掉(self):
        # 这是软断言最大的坑，用例里忘了最后一行，失败就永远发现不了。
        # 这条用例把这个行为固定下来，提醒所有人别忘。
        sa = SoftAssert()
        sa.equal(1, 2, "会被吞掉的失败")
        assert len(sa.failures) == 1      # 已经记录了

    def test_可以重复调用assert_all(self):
        sa = SoftAssert()
        sa.equal(1, 2, "x")
        for _ in range(2):
            with pytest.raises(AssertionError):
                sa.assert_all()
