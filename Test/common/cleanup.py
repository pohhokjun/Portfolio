# -*- coding: utf-8 -*-
"""
测试数据清理台账

【来源】从原 17_测试/core/cleanup.py 迁移。

★ 解决的问题（面试高频）★
    自动化跑一年，被测系统里会堆积几万条垃圾数据。
    这是自动化团队和业务团队最容易起冲突的地方。

    普通做法：在 fixture 的 teardown 里删掉。
    问题：如果进程被强杀，teardown 不会执行，数据就残留了。

    本模块的做法：
        1. 每创建一条数据就登记到「台账」文件（立即落盘）
        2. 结束时逆序执行清理（后创建的先删，避免外键依赖问题）
        3. 清理失败或没有清理方式的，留在台账里等人工处理
        4. 下次启动可以查看历史遗留台账

    面试话术：
        「测试数据管理我做了两层：fixture 负责正常路径的清理，
          台账负责异常退出时的兜底。台账是立即落盘的，
          即使进程被 kill，下次启动也能查到哪些数据没清干净。」
"""

import json
import time

from config.settings import get_config, ROOT
from common.logger import get_logger

log = get_logger("cleanup")


class CleanupRegistry:
    def __init__(self, cfg=None, run_id="default"):
        self.cfg = cfg or get_config()
        self.run_id = run_id

        cl = self.cfg.get("cleanup", {}) or {}
        self.enabled = bool(cl.get("enabled", True))
        self.test_prefix = cl.get("test_prefix", "qa_auto")

        state_dir = ROOT / "reports" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_path = state_dir / ("cleanup_%s.json" % run_id)

        self._items = []
        self._callbacks = []

    # -----------------------------------------------------------
    # 登记
    # -----------------------------------------------------------
    def track(self, kind, ident, meta=None, remover=None):
        """
        登记一条待清理的数据。

        参数：
            kind     数据类型，如 "account" / "order"
            ident    数据标识，如邮箱、订单号
            remover  清理函数，不传则只登记不自动清理
        """
        item = {"kind": kind, "id": ident, "meta": meta or {},
                "ts": time.time(), "done": False}
        self._items.append(item)
        if remover:
            self._callbacks.append((item, remover))
        self._flush()
        return item

    def defer(self, fn, desc=""):
        """登记一个延迟执行的清理动作。"""
        item = {"kind": "callback", "id": desc or getattr(fn, "__name__", "fn"),
                "meta": {}, "ts": time.time(), "done": False}
        self._items.append(item)
        self._callbacks.append((item, fn))
        return item

    def _flush(self):
        """立即落盘。进程被强杀也不丢台账。"""
        try:
            with open(self.ledger_path, "w", encoding="utf-8") as f:
                json.dump({"run_id": self.run_id, "items": self._items},
                          f, ensure_ascii=False, indent=2)
        except Exception as exc:
            log.warning("清理台账写入失败: %s", exc)

    # -----------------------------------------------------------
    # 执行清理
    # -----------------------------------------------------------
    def run(self, force=False):
        if not self.enabled and not force:
            log.info("清理已关闭，保留 %d 条测试数据（台账: %s）",
                     len(self._items), self.ledger_path)
            return {"total": len(self._items), "done": 0,
                    "failed": 0, "skipped": len(self._items)}

        done, failed = 0, 0
        # 逆序：后创建的先删，避免依赖问题
        for item, fn in reversed(self._callbacks):
            if item.get("done"):
                continue
            try:
                fn()
                item["done"] = True
                done += 1
            except Exception as exc:
                failed += 1
                item["error"] = str(exc)
                log.warning("清理失败 %s/%s: %s", item["kind"], item["id"], exc)

        self._flush()
        leftover = [i for i in self._items
                    if not i["done"] and i["kind"] != "callback"]
        if leftover:
            log.warning("有 %d 条数据无自动清理方式，请人工处理，台账: %s",
                        len(leftover), self.ledger_path)
        log.info("清理完成：成功 %d，失败 %d", done, failed)
        return {"total": len(self._items), "done": done,
                "failed": failed, "skipped": len(leftover)}

    def summary(self):
        by_kind = {}
        for i in self._items:
            by_kind[i["kind"]] = by_kind.get(i["kind"], 0) + 1
        return by_kind

    # -----------------------------------------------------------
    # 历史遗留台账
    # -----------------------------------------------------------
    @staticmethod
    def pending_ledgers(cfg=None):
        """查询所有还有未清理数据的历史台账。"""
        state_dir = ROOT / "reports" / "state"
        if not state_dir.exists():
            return []
        out = []
        for p in state_dir.glob("cleanup_*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                left = [i for i in d.get("items", []) if not i.get("done")]
                if left:
                    out.append({"path": str(p), "run_id": d.get("run_id"),
                                "pending": len(left)})
            except Exception:
                continue
        return out
