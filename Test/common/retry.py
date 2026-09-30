# -*- coding: utf-8 -*-
"""
重试与等待工具

【来源】从原 17_测试/core/retry.py 迁移。

★ 关键设计：只重试「瞬时故障」，不重试「真失败」★

    很多人的重试写法是「失败就重试」，这是错的：
    如果是真的功能缺陷，重试 3 次只是把失败拖慢 3 倍，
    更糟的是可能掩盖间歇性缺陷。

    正确做法：只对网络超时、元素未附着这类瞬时故障重试。
    断言失败绝不重试。

    面试话术：
        「重试要区分瞬时故障和真失败。我的 is_transient 里
          只匹配 timeout、connection、element not attached 这类关键词，
          断言失败直接抛出，不会被重试掩盖。」

注意：pytest-rerunfailures 提供的是「用例级」重试，
      本模块是「操作级」重试，两者互补。
"""

import functools
import time

from common.logger import get_logger

log = get_logger("retry")


class RetryExhausted(Exception):
    pass


# 只有匹配这些关键词的异常才会被重试
TRANSIENT_KEYWORDS = (
    "timeout",
    "net::err",
    "connection",
    "target closed",
    "navigation",
    "element is not attached",
    "detached",
    "temporarily",
    "econnreset",
    "read timed out",
)


def is_transient(exc):
    """判断异常是否属于可重试的瞬时故障。"""
    text = ("%s %s" % (type(exc).__name__, exc)).lower()
    return any(k in text for k in TRANSIENT_KEYWORDS)


def retry(times=3, delay=1.0, backoff=2.0, max_delay=15.0,
          only_transient=True, on_retry=None):
    """
    装饰器写法：

        @retry(times=3)
        def do_something():
            ...
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            wait = delay
            last = None
            for i in range(1, max(1, times) + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    last = exc
                    # 不是瞬时故障，直接抛出，不重试
                    if only_transient and not is_transient(exc):
                        raise
                    if i >= times:
                        break
                    log.warning("第 %d/%d 次失败，%ss 后重试: %s",
                                i, times, round(wait, 1), exc)
                    if on_retry:
                        try:
                            on_retry(i, exc)
                        except Exception:
                            pass
                    time.sleep(wait)
                    wait = min(wait * backoff, max_delay)
            raise RetryExhausted("重试 %d 次仍失败: %s" % (times, last)) from last
        return wrapper
    return deco


def wait_until(cond, timeout=20.0, interval=0.5, desc="条件"):
    """
    轮询等待某个条件成立。

    比 sleep 好在哪：
        sleep(5) 是「不管好没好都等5秒」
        wait_until 是「好了就走，最多等5秒」
        前者浪费时间，后者又快又稳。
    """
    end = time.time() + timeout
    last_exc = None
    while time.time() < end:
        try:
            val = cond()
            if val:
                return val
        except Exception as exc:
            last_exc = exc
        time.sleep(interval)
    raise TimeoutError("等待超时(%ss): %s%s"
                       % (timeout, desc,
                          (" / %s" % last_exc) if last_exc else ""))


def wait_stable(getter, stable_for=1.0, timeout=20.0, interval=0.3):
    """
    等待某个值稳定不变。

    典型场景：等待列表加载完成 —— 数量不再变化就说明加载完了。
    比等固定时间更可靠。
    """
    end = time.time() + timeout
    last = object()
    since = None
    while time.time() < end:
        cur = getter()
        if cur == last:
            if since is None:
                since = time.time()
            elif time.time() - since >= stable_for:
                return cur
        else:
            last = cur
            since = None
        time.sleep(interval)
    return last
