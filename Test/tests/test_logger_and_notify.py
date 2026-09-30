# -*- coding: utf-8 -*-
"""日志和通知的自测。"""

import logging

import pytest

from common import notify as N
from common.logger import ROOT_NAME, get_logger
from common.notify import Notifier


class TestLogger:
    """
    ★ 这一组是回归用例，钉住一个真实发生过的 bug ★

    原来的写法是把 handler 挂在名为 "qa" 的 logger 上，
    但 get_logger("api") 返回的是 logging.getLogger("api")。
    logging 靠名字里的点号建立父子关系，"api" 的父节点是 root 而不是 "qa"，
    所以 handler 一个都没生效 —— 整个项目的日志文件全程 0 字节，
    跑了几百次用例没有一个人发现。

    日志失效是「静默失败」的典型：不报错、不影响用例结果，
    只在你真正需要排查偶发失败的那天，发现什么记录都没有。
    """

    def test_子logger必须挂在qa命名空间下(self):
        assert get_logger("api").name == "qa.api"
        assert get_logger("page").name == "qa.page"

    def test_不带参数时就是qa本身(self):
        assert get_logger().name == ROOT_NAME

    def test_已经带前缀的不重复拼(self):
        assert get_logger("qa.api").name == "qa.api"

    def test_子logger能通过父节点拿到handler(self):
        # 这才是判断日志有没有真的生效的标准
        log = get_logger("随便什么模块")
        assert log.parent.name == ROOT_NAME
        assert log.parent.handlers, "qa 上没有 handler，日志会全部丢失"

    def test_日志真的写得进去(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="qa"):
            get_logger("api").info("这条一定要能被收到")
        assert "这条一定要能被收到" in caplog.text

    def test_保持propagate否则pytest的日志文件收不到(self):
        assert logging.getLogger(ROOT_NAME).propagate is True

    def test_重复调用不会把handler越加越多(self):
        before = len(logging.getLogger(ROOT_NAME).handlers)
        for i in range(5):
            get_logger("m%d" % i)
        assert len(logging.getLogger(ROOT_NAME).handlers) == before


class TestNotifierShouldSend:

    def _n(self, make_cfg, **conf):
        base = {"enabled": True, "on": ["fail"]}
        base.update(conf)
        return Notifier(make_cfg({"notify": base}))

    def test_关掉时不发(self, make_cfg):
        assert self._n(make_cfg, enabled=False).should_send({"failed": 9}) is False

    def test_只在失败时发_有失败就发(self, make_cfg):
        assert self._n(make_cfg).should_send({"failed": 1}) is True

    def test_只在失败时发_有异常也发(self, make_cfg):
        assert self._n(make_cfg).should_send({"error": 1}) is True

    def test_只在失败时发_全通过就不发(self, make_cfg):
        # 避免通知疲劳：天天发绿色报告，真出事的时候没人看
        assert self._n(make_cfg).should_send({"failed": 0, "error": 0}) is False

    def test_always每次都发(self, make_cfg):
        assert self._n(make_cfg, on=["always"]).should_send({"failed": 0}) is True

    def test_没配notify段时默认不发(self, make_cfg):
        assert Notifier(make_cfg({})).should_send({"failed": 1}) is False


class TestNotifierText:

    def _n(self, make_cfg):
        return Notifier(make_cfg({"notify": {"enabled": True}}))

    def test_通过率计算(self, make_cfg):
        text = self._n(make_cfg).build_text(
            {"env": "test", "duration": 12.3},
            {"total": 10, "passed": 8, "failed": 2, "error": 0, "skipped": 0})
        assert "通过率: 80.0%" in text
        assert "用例: 10" in text
        assert "test" in text

    def test_一条用例都没有时不能除零(self, make_cfg):
        text = self._n(make_cfg).build_text({}, {"total": 0, "passed": 0})
        assert "通过率: 0.0%" in text

    def test_列出失败用例(self, make_cfg):
        text = self._n(make_cfg).build_text(
            {"failures": ["test_a", "test_b"]}, {"total": 2, "passed": 0})
        assert "test_a" in text and "test_b" in text

    def test_失败太多时只列前十条(self, make_cfg):
        text = self._n(make_cfg).build_text(
            {"failures": ["t%d" % i for i in range(15)]}, {"total": 15})
        assert "其余 5 条见报告" in text

    def test_带上报告路径(self, make_cfg):
        text = self._n(make_cfg).build_text({"report": "reports/report.html"}, {})
        assert "reports/report.html" in text


class TestNotifierSend:

    def test_没配任何渠道时不发只打印(self, make_cfg):
        res = Notifier(make_cfg({"notify": {"enabled": True, "on": ["always"]}})).send(
            {}, {"total": 1, "passed": 1})
        assert res["sent"] is False and "text" in res

    def test_不满足条件时直接返回(self, make_cfg):
        res = Notifier(make_cfg({"notify": {"enabled": True}})).send(
            {}, {"failed": 0, "error": 0})
        assert res == {"sent": False, "reason": "未触发通知条件"}

    def test_force能绕过条件判断(self, make_cfg):
        res = Notifier(make_cfg({"notify": {"enabled": False}})).send(
            {}, {"failed": 0}, force=True)
        assert res["reason"] == "无可用渠道"      # 说明已经走到发送逻辑了

    def test_webhook调用一次并带上自定义头(self, make_cfg, monkeypatch):
        calls = []

        class R:
            status_code = 200

        monkeypatch.setattr(N.requests, "post",
                            lambda url, **kw: calls.append((url, kw)) or R())
        res = Notifier(make_cfg({"notify": {
            "enabled": True, "on": ["always"],
            "webhook": {"url": "http://钩子", "headers": {"X-Token": "abc"},
                        "extra": {"msg_type": "text"}}}})).send(
            {"env": "test"}, {"total": 1, "passed": 1})
        assert res["sent"] is True and res["channels"]["webhook"] == "ok"
        assert calls[0][0] == "http://钩子"
        assert calls[0][1]["headers"] == {"X-Token": "abc"}
        assert calls[0][1]["json"]["msg_type"] == "text"

    def test_通知发不出去不能把测试搞挂(self, make_cfg, monkeypatch):
        # 通知只是锦上添花，绝不能因为它让整轮测试结果丢失
        def boom(*a, **kw):
            raise ConnectionError("钩子地址不通")

        monkeypatch.setattr(N.requests, "post", boom)
        res = Notifier(make_cfg({"notify": {
            "enabled": True, "on": ["always"],
            "webhook": {"url": "http://钩子"}}})).send({}, {"total": 1})
        assert "钩子地址不通" in res["channels"]["webhook"]

    def test_telegram缺token时给出明确原因(self, make_cfg):
        res = Notifier(make_cfg({"notify": {
            "enabled": True, "on": ["always"],
            "telegram": {"enabled": True, "token": "", "chat_id": ""}}})).send(
            {}, {"total": 1})
        assert res["channels"]["telegram"] == "缺少 token/chat_id"
