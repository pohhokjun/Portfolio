# -*- coding: utf-8 -*-
"""账号池的自测。

账号池要解决的是并行执行抢账号。测这块的难点在于「并发」，
但并发行为的本质是「状态文件里有没有别人的有效租约」，
所以直接构造状态文件就能把每种情况测全，不用真的开多进程。
"""

import json
import os

import pytest

from common.account_pool import AccountPool, NoAccountAvailable

ACCOUNTS = [
    {"username": "u1@x.com", "password": "p1", "role": "admin", "tags": ["full"]},
    {"username": "u2@x.com", "password": "p2", "role": "user", "tags": ["readonly"]},
]


@pytest.fixture
def pool(sandbox, make_cfg):
    def _pool(accounts=None, **pool_cfg):
        conf = {"lease_ttl": 1800, "wait_timeout": 1}
        conf.update(pool_cfg)
        return AccountPool(make_cfg({
            "accounts": ACCOUNTS if accounts is None else accounts,
            "account_pool": conf,
        }))
    return _pool


class TestAcquire:

    def test_能借到账号(self, pool):
        assert pool().acquire()["username"] == "u1@x.com"

    def test_借出的是副本改了不影响池子(self, pool):
        p = pool()
        acc = p.acquire()
        acc["password"] = "被改了"
        assert p.accounts[0]["password"] == "p1"

    def test_按角色筛选(self, pool):
        assert pool().acquire(role="user")["username"] == "u2@x.com"

    def test_按标签筛选(self, pool):
        assert pool().acquire(tags=["readonly"])["username"] == "u2@x.com"

    def test_没有符合条件的账号直接报错(self, pool):
        with pytest.raises(NoAccountAvailable) as e:
            pool().acquire(role="根本没有这个角色")
        assert "没有符合条件的账号" in str(e.value)

    def test_没配账号时报错(self, pool):
        with pytest.raises(NoAccountAvailable):
            pool(accounts=[]).acquire()

    def test_第一个被占了会拿第二个(self, pool):
        p = pool()
        first = p.acquire()
        # 伪造成别的进程持有，本进程就该跳过它
        state = json.loads(p.state_path.read_text(encoding="utf-8"))
        state[first["username"]]["pid"] = os.getpid() + 12345
        p.state_path.write_text(json.dumps(state), encoding="utf-8")
        assert p.acquire()["username"] == "u2@x.com"

    def test_全被别的进程占着就等到超时(self, pool):
        p = pool(wait_timeout=0)
        state = {a["username"]: {"ts": 9e18, "pid": os.getpid() + 12345}
                 for a in ACCOUNTS}
        p.state_path.write_text(json.dumps(state), encoding="utf-8")
        with pytest.raises(NoAccountAvailable) as e:
            p.acquire()
        assert "等待账号超时" in str(e.value)

    def test_租约过期的账号可以被别人拿走(self, pool):
        # 这是 TTL 存在的意义：进程崩了不会让账号被永久占用
        p = pool(lease_ttl=1)
        state = {"u1@x.com": {"ts": 0, "pid": os.getpid() + 12345}}
        p.state_path.write_text(json.dumps(state), encoding="utf-8")
        assert p.acquire()["username"] == "u1@x.com"

    def test_自己持有的账号可以再拿(self, pool):
        p = pool()
        assert p.acquire()["username"] == p.acquire()["username"]


class TestRelease:

    def test_归还后状态文件里没有了(self, pool):
        p = pool()
        acc = p.acquire()
        p.release(acc)
        assert json.loads(p.state_path.read_text(encoding="utf-8")) == {}

    def test_归还可以只传用户名(self, pool):
        p = pool()
        p.acquire()
        p.release("u1@x.com")
        assert p._held == []

    def test_归还没借过的账号不报错(self, pool):
        pool().release("没借过的@x.com")

    def test_release_all归还全部(self, pool):
        p = pool()
        p.acquire(role="admin")
        p.acquire(role="user")
        p.release_all()
        assert json.loads(p.state_path.read_text(encoding="utf-8")) == {}
        assert p._held == []


class TestStatus:

    def test_没人占用时全是空闲(self, pool):
        assert [r["status"] for r in pool().status()] == ["空闲", "空闲"]

    def test_占用中的会标出来(self, pool):
        p = pool()
        p.acquire()
        rows = {r["username"]: r for r in p.status()}
        assert rows["u1@x.com"]["status"] == "占用中"
        assert rows["u1@x.com"]["since"]      # 有占用时间
        assert rows["u2@x.com"]["status"] == "空闲"

    def test_租约过期算空闲(self, pool):
        p = pool(lease_ttl=1)
        p.state_path.write_text(json.dumps({"u1@x.com": {"ts": 0, "pid": 1}}),
                                encoding="utf-8")
        assert [r["status"] for r in p.status()] == ["空闲", "空闲"]


class TestLeaseContextManager:

    def test_用完自动归还(self, pool):
        p = pool()
        with p.lease() as acc:
            assert acc["username"] == "u1@x.com"
        assert json.loads(p.state_path.read_text(encoding="utf-8")) == {}

    def test_用例内部抛异常也会归还(self, pool):
        p = pool()
        with pytest.raises(ValueError):
            with p.lease():
                raise ValueError("用例挂了")
        assert json.loads(p.state_path.read_text(encoding="utf-8")) == {}


class TestStateFile:

    def test_状态文件按环境隔离(self, sandbox, make_cfg):
        cfg_a = make_cfg({"accounts": ACCOUNTS}, env="test")
        cfg_b = make_cfg({"accounts": ACCOUNTS}, env="prod")
        assert AccountPool(cfg_a).state_path != AccountPool(cfg_b).state_path

    def test_状态文件损坏时当空处理而不是崩(self, pool):
        p = pool()
        p.state_path.write_text("这不是 json", encoding="utf-8")
        assert p.acquire()["username"] == "u1@x.com"
