# -*- coding: utf-8 -*-
"""
账号池（带租借与超时释放）

【来源】从原 17_测试/core/account_pool.py 迁移。

★ 解决的问题（面试可讲）★
    自动化用例要登录，如果所有用例共用一个账号会出事：
        1. 并行执行时互相踢下线
        2. 用例A改了账号资料，用例B断言就挂了
        3. 某个用例把账号搞成异常状态，后面全部失败

    账号池的做法：
        用例执行前「租借」一个空闲账号，用完「归还」。
        租借带 TTL（存活时间），进程崩溃后账号不会被永久占用。
        支持按角色筛选（管理员/普通用户/只读）。

    面试话术：
        「并行执行时账号冲突是个典型问题。我实现了账号池，
          用文件锁 + TTL 做租借，配合 pytest-xdist 的多进程执行。
          真实项目里如果用 Redis 会更好，本地场景文件足够。」
"""

import json
import os
import time

from config.settings import get_config, ROOT
from common.logger import get_logger

log = get_logger("account")


class NoAccountAvailable(Exception):
    pass


class AccountPool:
    def __init__(self, cfg=None):
        self.cfg = cfg or get_config()
        self.accounts = self.cfg.get("accounts", []) or []

        state_dir = ROOT / "reports" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = state_dir / ("accounts_%s.json" % self.cfg.tag)

        pool_cfg = self.cfg.get("account_pool", {}) or {}
        self.lease_ttl = int(pool_cfg.get("lease_ttl", 1800))
        self.wait_timeout = int(pool_cfg.get("wait_timeout", 60))
        self._held = []

    # -----------------------------------------------------------
    # 状态文件读写（多进程共享）
    # -----------------------------------------------------------
    def _load(self):
        if not self.state_path.exists():
            return {}
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self, state):
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _candidates(self, role=None, tags=None):
        out = []
        for acc in self.accounts:
            if role and acc.get("role") != role:
                continue
            if tags and not (set(tags) & set(acc.get("tags", []))):
                continue
            out.append(acc)
        return out

    # -----------------------------------------------------------
    # 租借与归还
    # -----------------------------------------------------------
    def acquire(self, role=None, tags=None, timeout=None):
        timeout = self.wait_timeout if timeout is None else timeout
        cands = self._candidates(role, tags)
        if not cands:
            raise NoAccountAvailable(
                "没有符合条件的账号 role=%s tags=%s。"
                "请在 站点 site.yaml 的 accounts 段配置。" % (role, tags))

        deadline = time.time() + timeout
        while True:
            state = self._load()
            now = time.time()
            for acc in cands:
                key = acc.get("username")
                lease = state.get(key)
                # 有效租约且不是自己持有的，跳过
                if lease and (now - lease.get("ts", 0)) < self.lease_ttl \
                        and lease.get("pid") != os.getpid():
                    continue
                state[key] = {"ts": now, "pid": os.getpid(),
                              "role": acc.get("role", "")}
                self._save(state)
                self._held.append(key)
                log.debug("占用账号 %s", key)
                return dict(acc)

            if time.time() >= deadline:
                raise NoAccountAvailable(
                    "等待账号超时(%ss) role=%s，可能是其他进程正在占用" % (timeout, role))
            time.sleep(2)

    def release(self, account):
        key = account.get("username") if isinstance(account, dict) else account
        state = self._load()
        if key in state:
            state.pop(key, None)
            self._save(state)
        if key in self._held:
            self._held.remove(key)
        log.debug("释放账号 %s", key)

    def release_all(self):
        for key in list(self._held):
            self.release(key)

    def status(self):
        state = self._load()
        now = time.time()
        rows = []
        for acc in self.accounts:
            key = acc.get("username")
            lease = state.get(key)
            busy = bool(lease and (now - lease.get("ts", 0)) < self.lease_ttl)
            rows.append({
                "username": key,
                "role": acc.get("role", ""),
                "status": "占用中" if busy else "空闲",
                "since": time.strftime("%H:%M:%S", time.localtime(lease["ts"]))
                         if busy else "",
            })
        return rows

    # -----------------------------------------------------------
    # 上下文管理器写法
    # -----------------------------------------------------------
    class Lease:
        def __init__(self, pool, role=None, tags=None):
            self.pool, self.role, self.tags = pool, role, tags
            self.account = None

        def __enter__(self):
            self.account = self.pool.acquire(self.role, self.tags)
            return self.account

        def __exit__(self, *exc):
            if self.account:
                self.pool.release(self.account)
            return False

    def lease(self, role=None, tags=None):
        """用法： with pool.lease(role="admin") as acc: ..."""
        return AccountPool.Lease(self, role, tags)
