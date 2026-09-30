# -*- coding: utf-8 -*-
"""
钱包：被测对象就是这个假服务本身（资金链路），框架骨架在 tools/mock_server.py。

    automationexercise 没有钱，但游戏/支付公司的测试岗考的全是钱：
    充值、提现、重复提交、并发、对账。所以造一个最小钱包，配合 BUGS 做对照实验。
"""

import threading
import time
from contextlib import nullcontext
from decimal import Decimal, InvalidOperation

from tools.mock_server import MockRoutes

# 单笔上限（分）。边界值用例要卡 50000.00 和 50000.01 两个点
WALLET_MAX_CENTS = 5_000_000

# 可埋的缺陷。每一种都是资金系统线上真出过的事故，
# 用来做对照实验：同一套检查，打正常版必须绿、打有 bug 的版本必须红。
BUGS = {
    "no_idem": "不校验订单号：网络重试一次，钱就加两次",
    "race": "读余额和写余额之间不加锁：并发提现能扣成负数",
    "float": "用浮点数存钱：0.1 + 0.2 = 0.30000000000000004",
    "ledger_gap": "提现不记流水：余额和流水对不上账",
}


def _to_cents(raw):
    """
    元 → 分。不合法返回 None。

    钱一律用整数「分」存，入口用 Decimal 解析 ——
    float 连 0.1 都存不准，累加几次就会差出一分钱，
    对账时这一分钱要花一整天去查。
    """
    try:
        d = Decimal(str(raw))
    except InvalidOperation:
        return None
    # exponent < -2 说明超过两位小数（0.001），不能悄悄四舍五入吞掉
    if not d.is_finite() or d <= 0 or d.as_tuple().exponent < -2:
        return None
    cents = int(d * 100)
    return cents if cents <= WALLET_MAX_CENTS else None


def _yuan(bal):
    # 负数要先取绝对值再拆：divmod(-2050, 100) 是 (-21, 50)，
    # 直接拼会把 -20.50 写成 -21.50。这个 bug 是对账检查第一次跑就抓出来的。
    if isinstance(bal, float):
        return repr(bal)
    return ("-" if bal < 0 else "") + "%d.%02d" % divmod(abs(bal), 100)


class Routes(MockRoutes):
    BUGS = BUGS

    @staticmethod
    def init_server(srv):
        srv.wallets = {}
        srv.wallet_lock = threading.Lock()

    def _h_wallet_deposit(self, method, query, body):
        self._wallet_op(method, body, +1)

    def _h_wallet_withdraw(self, method, query, body):
        self._wallet_op(method, body, -1)

    def _h_wallet_balance(self, method, query, body):
        w = self.server.wallets.get(query.get("user"))
        if not w:
            return self._biz(404, message="Wallet not found!")
        self._biz(200, balance=_yuan(w["bal"]))

    def _h_wallet_ledger(self, method, query, body):
        w = self.server.wallets.get(query.get("user"))
        if not w:
            return self._biz(404, message="Wallet not found!")
        self._biz(200, ledger=w["ledger"])

    def _wallet_op(self, method, body, sign):
        if method != "POST":
            return self._biz(405, message="This request method is not supported.")
        user, order = body.get("user"), body.get("order_id")
        if not user or not order:
            return self._biz(400, message="Bad request, user or order_id is missing.")
        cents = _to_cents(body.get("amount"))
        if cents is None:
            return self._biz(400, message="Invalid amount!")

        srv, bugs = self.server, self.server.bugs
        with nullcontext() if "race" in bugs else srv.wallet_lock:
            w = srv.wallets.setdefault(user, {"bal": 0, "ledger": [], "orders": {}})
            # 幂等：同一个订单号再来一次，原样返回上次的结果，不再动钱。
            # 客户端超时重试、用户连点两下、网关重放，都会产生重复请求。
            if order in w["orders"] and "no_idem" not in bugs:
                return self._send(w["orders"][order])
            amt = float(body["amount"]) if "float" in bugs else cents
            bal = w["bal"]
            # 读和写之间留一个窗口，真实系统里这里是一次数据库往返。
            # 不加锁的时候，并发请求会读到同一个旧余额。
            time.sleep(0.005)
            if sign < 0 and bal < amt:
                result = {"responseCode": 400, "message": "Insufficient balance!",
                          "balance": _yuan(bal)}
            else:
                w["bal"] = bal + sign * amt
                if not (sign < 0 and "ledger_gap" in bugs):
                    w["ledger"].append({"order_id": order,
                                        "amount": _yuan(sign * amt)})
                result = {"responseCode": 200, "balance": _yuan(w["bal"])}
            w["orders"][order] = result
        self._send(result)
