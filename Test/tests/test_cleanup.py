# -*- coding: utf-8 -*-
"""测试数据清理台账的自测。

清理这块出问题不会让用例变红，只会让被测系统慢慢堆满垃圾数据，
等到业务同事来投诉的时候已经几万条了。所以必须有自测兜住。
"""

import json

from common.cleanup import CleanupRegistry


def registry(sandbox, make_cfg, **cleanup):
    conf = {"enabled": True, "test_prefix": "qa_auto"}
    conf.update(cleanup)
    return CleanupRegistry(make_cfg({"cleanup": conf}), run_id="r1")


class TestTrack:

    def test_登记后立刻落盘(self, sandbox, make_cfg):
        # 关键行为：进程被 kill 也要能查到残留数据
        reg = registry(sandbox, make_cfg)
        reg.track("account", "a@x.com")
        data = json.loads(reg.ledger_path.read_text(encoding="utf-8"))
        assert data["run_id"] == "r1"
        assert data["items"][0]["id"] == "a@x.com"
        assert data["items"][0]["done"] is False

    def test_按类型统计(self, sandbox, make_cfg):
        reg = registry(sandbox, make_cfg)
        reg.track("account", "a")
        reg.track("account", "b")
        reg.track("order", "o1")
        assert reg.summary() == {"account": 2, "order": 1}

    def test_defer登记一个回调(self, sandbox, make_cfg):
        reg = registry(sandbox, make_cfg)
        item = reg.defer(lambda: None, desc="关掉开关")
        assert item["kind"] == "callback" and item["id"] == "关掉开关"

    def test_defer不传描述时用函数名(self, sandbox, make_cfg):
        def 我的清理函数():
            pass
        assert registry(sandbox, make_cfg).defer(我的清理函数)["id"] == "我的清理函数"


class TestRun:

    def test_有remover的会被执行(self, sandbox, make_cfg):
        done = []
        reg = registry(sandbox, make_cfg)
        reg.track("account", "a", remover=lambda: done.append("a"))
        res = reg.run()
        assert done == ["a"]
        assert res == {"total": 1, "done": 1, "failed": 0, "skipped": 0}

    def test_逆序清理后创建的先删(self, sandbox, make_cfg):
        # 订单挂在账号下，得先删订单再删账号，否则外键报错
        order = []
        reg = registry(sandbox, make_cfg)
        reg.track("account", "a", remover=lambda: order.append("账号"))
        reg.track("order", "o", remover=lambda: order.append("订单"))
        reg.run()
        assert order == ["订单", "账号"]

    def test_某条清理失败不影响其他条(self, sandbox, make_cfg):
        done = []
        reg = registry(sandbox, make_cfg)
        reg.track("a", "1", remover=lambda: done.append(1))
        reg.track("b", "2", remover=lambda: (_ for _ in ()).throw(RuntimeError("删不掉")))
        res = reg.run()
        assert done == [1]
        assert res["done"] == 1 and res["failed"] == 1

    def test_失败原因写进台账(self, sandbox, make_cfg):
        reg = registry(sandbox, make_cfg)
        reg.track("b", "2", remover=lambda: (_ for _ in ()).throw(RuntimeError("删不掉")))
        reg.run()
        data = json.loads(reg.ledger_path.read_text(encoding="utf-8"))
        assert "删不掉" in data["items"][0]["error"]

    def test_没有remover的只登记不清理(self, sandbox, make_cfg):
        reg = registry(sandbox, make_cfg)
        reg.track("account", "手工建的账号")
        res = reg.run()
        assert res["done"] == 0 and res["skipped"] == 1

    def test_关掉清理时全部保留(self, sandbox, make_cfg):
        done = []
        reg = registry(sandbox, make_cfg, enabled=False)
        reg.track("a", "1", remover=lambda: done.append(1))
        res = reg.run()
        assert done == []
        assert res["skipped"] == 1

    def test_关掉清理也能用force强制执行(self, sandbox, make_cfg):
        done = []
        reg = registry(sandbox, make_cfg, enabled=False)
        reg.track("a", "1", remover=lambda: done.append(1))
        reg.run(force=True)
        assert done == [1]

    def test_重复run不会清理两次(self, sandbox, make_cfg):
        done = []
        reg = registry(sandbox, make_cfg)
        reg.track("a", "1", remover=lambda: done.append(1))
        reg.run()
        reg.run()
        assert done == [1]

    def test_没有任何数据时run也不出错(self, sandbox, make_cfg):
        assert registry(sandbox, make_cfg).run()["total"] == 0


class TestPendingLedgers:

    def test_查得到有残留的历史台账(self, sandbox, make_cfg):
        reg = registry(sandbox, make_cfg)
        reg.track("account", "没清掉的")
        pending = CleanupRegistry.pending_ledgers()
        assert len(pending) == 1
        assert pending[0]["run_id"] == "r1" and pending[0]["pending"] == 1

    def test_全部清干净的台账不再列出(self, sandbox, make_cfg):
        reg = registry(sandbox, make_cfg)
        reg.track("a", "1", remover=lambda: None)
        reg.run()
        assert CleanupRegistry.pending_ledgers() == []

    def test_台账文件损坏时跳过而不是崩(self, sandbox, make_cfg):
        registry(sandbox, make_cfg)
        bad = sandbox / "reports" / "state" / "cleanup_坏文件.json"
        bad.write_text("这不是 json", encoding="utf-8")
        CleanupRegistry.pending_ledgers()      # 不抛异常即可
