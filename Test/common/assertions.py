# -*- coding: utf-8 -*-
"""
断言模块

包含两部分：
    1. 普通断言函数 —— 带 Allure 步骤记录，报告里能看到每一次断言
    2. SoftAssert 软断言 —— 一次跑完收集所有失败，而不是第一个失败就中断

关于软断言（面试高频）：
    pytest 原生 assert 是「硬断言」，失败立即抛异常，后面的检查点不再执行。
    比如一个页面要检查 10 个元素，第 2 个挂了，你不知道后面 8 个是好是坏，
    要修 3 轮才能全部暴露。软断言一轮就能拿到全部问题。

    代价：软断言写起来啰嗦，且不能中断危险操作。
    实践：关键前置条件用硬断言，页面多点校验用软断言。

【第二期融合点】
    这个 SoftAssert 是从 17_测试/core/assertion.py 移植过来的，
    保留了原有 API，并加上了 Allure 报告集成。
"""

import allure


# ---------------------------------------------------------------
# 硬断言：包一层，让 Allure 报告能看到断言过程
# ---------------------------------------------------------------
def assert_equal(actual, expected, msg=""):
    with allure.step("断言相等: %s" % (msg or "")):
        assert actual == expected, \
            "%s\n  期望: %r\n  实际: %r" % (msg, expected, actual)


def assert_in(member, container, msg=""):
    with allure.step("断言包含: %s" % (msg or "")):
        assert member in container, \
            "%s\n  期望包含: %r\n  实际内容: %r" % (msg, member, str(container)[:300])


def assert_not_in(member, container, msg=""):
    with allure.step("断言不包含: %s" % (msg or "")):
        assert member not in container, \
            "%s\n  不应包含: %r" % (msg, member)


def assert_true(condition, msg=""):
    with allure.step("断言为真: %s" % (msg or "")):
        assert condition, msg or "断言失败：条件为假"


def assert_status_code(actual, expected, msg="HTTP状态码"):
    """接口测试专用。expected 可以是单个数字或列表。"""
    allowed = expected if isinstance(expected, (list, tuple, set)) else [expected]
    with allure.step("断言状态码 %s 属于 %s" % (actual, list(allowed))):
        assert actual in allowed, \
            "%s 不符\n  期望: %s\n  实际: %s" % (msg, list(allowed), actual)


def assert_less_than(actual, limit, msg="耗时"):
    with allure.step("断言 %s < %s" % (actual, limit)):
        assert actual is not None and actual < limit, \
            "%s 超标\n  阈值: %s\n  实际: %s" % (msg, limit, actual)


# ---------------------------------------------------------------
# 软断言
# ---------------------------------------------------------------
class SoftAssert:
    """
    用法：
        sa = SoftAssert()
        sa.equal(a, b, "价格")
        sa.contains(text, "成功", "提示语")
        sa.assert_all()          # 最后统一判定，有失败才抛异常
    """

    def __init__(self):
        self.failures = []
        self.checks = 0

    def _record(self, ok, name, detail):
        self.checks += 1
        if ok:
            with allure.step("[通过] %s" % name):
                pass
        else:
            self.failures.append("%s -> %s" % (name, detail))
            with allure.step("[失败] %s : %s" % (name, detail)):
                pass
        return ok

    def true(self, condition, name, detail="条件为假"):
        return self._record(bool(condition), name, detail)

    def equal(self, actual, expected, name):
        return self._record(actual == expected, name,
                            "期望 %r，实际 %r" % (expected, actual))

    def not_equal(self, actual, expected, name):
        return self._record(actual != expected, name, "不应等于 %r" % (expected,))

    def contains(self, haystack, needle, name):
        return self._record(needle in (haystack or ""), name,
                            "未包含 %r" % (needle,))

    def not_contains(self, haystack, needle, name):
        return self._record(needle not in (haystack or ""), name,
                            "不应包含 %r" % (needle,))

    def status_code(self, actual, expected, name="状态码"):
        allowed = expected if isinstance(expected, (list, tuple, set)) else [expected]
        return self._record(actual in allowed, name,
                            "状态码 %s 不在 %s" % (actual, list(allowed)))

    def less_than(self, actual, limit, name):
        ok = actual is not None and actual < limit
        return self._record(ok, name, "%s 超过阈值 %s" % (actual, limit))

    def assert_all(self):
        """必须在用例最后调用，否则失败会被吞掉。"""
        if self.failures:
            detail = "\n".join("  %d) %s" % (i + 1, f)
                               for i, f in enumerate(self.failures))
            raise AssertionError(
                "软断言共 %d 个检查点，%d 个失败：\n%s"
                % (self.checks, len(self.failures), detail)
            )
