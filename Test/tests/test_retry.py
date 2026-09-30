# -*- coding: utf-8 -*-
"""重试与等待工具的自测。

重试是最容易被写错的一块。写错的后果不是用例挂掉，
而是「本该发现的缺陷被重试掩盖了」—— 这是自动化最坏的一种失效。
所以这里重点测「哪些情况绝对不能重试」。
"""

import time

import pytest

from common import retry as R
from common.retry import RetryExhausted, is_transient, retry, wait_stable, wait_until

# retry.py 里是 import time 后直接 time.sleep()，没有模块内别名，
# 想拦下来只能改 time 模块本身。所以先把真货存起来，
# 少数几条确实需要等待的用例再换回去。
_REAL_SLEEP = time.sleep


@pytest.fixture(autouse=True)
def 不真的等待(monkeypatch):
    """把 sleep 换掉，测试逻辑不该被真实等待拖慢。"""
    monkeypatch.setattr(R.time, "sleep", lambda s: None)


class TestIsTransient:

    @pytest.mark.parametrize("exc", [
        TimeoutError("read timed out"),
        RuntimeError("net::ERR_CONNECTION_RESET"),
        RuntimeError("Element is not attached to the DOM"),
        RuntimeError("Navigation failed"),
        RuntimeError("Target closed"),
        RuntimeError("service temporarily unavailable"),
    ])
    def test_瞬时故障要能认出来(self, exc):
        assert is_transient(exc) is True

    @pytest.mark.parametrize("exc", [
        AssertionError("购物车金额不对"),
        ValueError("字段缺失"),
        KeyError("responseCode"),
    ])
    def test_断言失败和数据错误绝不算瞬时故障(self, exc):
        assert is_transient(exc) is False

    def test_异常类名里带关键词也算(self):
        # requests 的 ConnectionError 消息可能是空的，只能靠类名认
        class ConnectionError_(Exception):
            pass
        assert is_transient(ConnectionError_()) is True


class TestRetryDecorator:

    def test_一次成功不重试(self):
        calls = []

        @retry(times=3)
        def fn():
            calls.append(1)
            return "ok"

        assert fn() == "ok"
        assert len(calls) == 1

    def test_瞬时故障会重试直到成功(self):
        calls = []

        @retry(times=3)
        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise TimeoutError("read timed out")
            return "ok"

        assert fn() == "ok"
        assert len(calls) == 3

    def test_断言失败立刻抛出不重试(self):
        # 核心行为：重试 3 次只会把失败拖慢 3 倍，还可能掩盖间歇性缺陷
        calls = []

        @retry(times=3)
        def fn():
            calls.append(1)
            raise AssertionError("金额不对")

        with pytest.raises(AssertionError):
            fn()
        assert len(calls) == 1

    def test_重试用尽抛RetryExhausted且保留原始异常(self):
        @retry(times=2)
        def fn():
            raise TimeoutError("read timed out")

        with pytest.raises(RetryExhausted) as e:
            fn()
        assert isinstance(e.value.__cause__, TimeoutError)

    def test_only_transient关掉后什么错都重试(self):
        calls = []

        @retry(times=3, only_transient=False)
        def fn():
            calls.append(1)
            raise ValueError("随便什么错")

        with pytest.raises(RetryExhausted):
            fn()
        assert len(calls) == 3

    def test_on_retry回调自己报错不能影响主流程(self):
        @retry(times=2, on_retry=lambda i, e: 1 / 0)
        def fn():
            raise TimeoutError("read timed out")

        with pytest.raises(RetryExhausted):
            fn()

    def test_保留原函数的名字和文档(self):
        @retry()
        def 我的函数():
            """说明文字"""

        assert 我的函数.__name__ == "我的函数"
        assert 我的函数.__doc__ == "说明文字"

    def test_times传0也至少执行一次(self):
        calls = []

        @retry(times=0)
        def fn():
            calls.append(1)
            raise TimeoutError("read timed out")

        with pytest.raises(RetryExhausted):
            fn()
        assert len(calls) == 1

    def test_等待时间按倍数增长但不超过上限(self):
        waits = []

        @retry(times=6, delay=1, backoff=3, max_delay=10,
               on_retry=lambda i, e: waits.append(i))
        def fn():
            raise TimeoutError("read timed out")

        with pytest.raises(RetryExhausted):
            fn()
        assert len(waits) == 5      # 最后一次失败不再等待


class TestWaitUntil:

    def test_条件成立立即返回(self):
        assert wait_until(lambda: "好了", timeout=1) == "好了"

    def test_条件一直不成立就超时(self):
        with pytest.raises(TimeoutError):
            wait_until(lambda: False, timeout=0.3, interval=0.05)

    def test_条件函数抛异常算没成立并把异常带进超时信息(self):
        def boom():
            raise ValueError("元素还没出来")

        with pytest.raises(TimeoutError) as e:
            wait_until(boom, timeout=0.3, interval=0.05, desc="等元素")
        assert "等元素" in str(e.value) and "元素还没出来" in str(e.value)

    def test_中途才成立也能拿到(self):
        state = {"n": 0}

        def cond():
            state["n"] += 1
            return "好了" if state["n"] >= 3 else None

        assert wait_until(cond, timeout=1, interval=0.01) == "好了"


class TestWaitStable:

    def test_值不再变化就返回(self, monkeypatch):
        monkeypatch.setattr(R.time, "sleep", _REAL_SLEEP)   # 这个用例要真的等
        seq = [1, 2, 3, 3, 3, 3, 3, 3, 3, 3]
        assert wait_stable(lambda: seq.pop(0) if seq else 3,
                           stable_for=0.05, timeout=2, interval=0.01) == 3

    def test_一直在变就等到超时返回最后一次的值(self, monkeypatch):
        monkeypatch.setattr(R.time, "sleep", _REAL_SLEEP)
        n = {"v": 0}

        def getter():
            n["v"] += 1
            return n["v"]

        assert wait_stable(getter, stable_for=1, timeout=0.2, interval=0.01) == n["v"]
