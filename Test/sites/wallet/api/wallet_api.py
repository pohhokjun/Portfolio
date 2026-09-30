# -*- coding: utf-8 -*-
"""
钱包接口（被测对象在 tools/mock_server.py）

每个实例绑一个新用户，用例之间余额互不干扰。
"""

import uuid

from api.base_api import BaseApi


class WalletApi:

    def __init__(self, cfg, url):
        self.cfg, self.url = cfg, url
        self.user = "u_" + uuid.uuid4().hex[:8]
        self.api = self.client()

    def client(self):
        # 并发用例每个线程要自己的 Session：requests.Session 不保证线程安全
        c = BaseApi(self.cfg, min_interval=0)
        c.base = self.url
        c.MAX_RETRY = 1
        return c

    def call(self, kind, amount, order=None, client=None):
        """kind 是 deposit / withdraw。不传订单号就生成一个新的。"""
        resp = (client or self.api).post(
            "/wallet/" + kind,
            json_body={"user": self.user, "amount": amount,
                       "order_id": order or uuid.uuid4().hex})
        return BaseApi.json_of(resp)

    def deposit(self, amount, order=None):
        return self.call("deposit", amount, order)

    def withdraw(self, amount, order=None, client=None):
        return self.call("withdraw", amount, order, client)

    def balance(self):
        return BaseApi.json_of(self.api.get(
            "/wallet/balance", params={"user": self.user}))["balance"]

    def ledger(self):
        return BaseApi.json_of(self.api.get(
            "/wallet/ledger", params={"user": self.user}))["ledger"]
